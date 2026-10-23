#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unity 真实代码覆盖率采集编排脚本。

pack-ref-ok: unity-pipeline —— 轮询脚本按该可选包是否安装分支（未安装跳过轮询并提示降级），不构成硬依赖。

凭据来源（全部经 P0 活体实测确认，详见 references/real-coverage-guide.md）：
  1. 状态读取必须走 `unity command script eval` 读内存真实值；
     实测同一时刻 Settings.json 为 true 而内存 Coverage.enabled 为 false，
     文件不能作为状态依据。
  2. 配置写入必须经 CodeCoverageWindow.AssembliesToInclude setter
     （内部走 CoveragePreferences.SetString -> Settings.Save 落盘）；
     直接反射调 SetString 会因 SettingsScope 参数不当而不落盘。
  3. 域重载必须用 EditorUtility.RequestScriptReload()；
     CompilationPipeline.RequestScriptCompilation() 实测无效（域哈希不变）。
  4. 域重载会用内存缓存反向覆盖磁盘文件，因此必须先写内存再重载。
  5. 非 batchmode 下程序集过滤只从偏好读，且不展开 <all> 别名，
     故必须写入显式程序集清单。

用法：
  python collect_real_coverage.py --dry-run          # 仅打印将执行的步骤
  python collect_real_coverage.py --confirm          # 实际执行（需显式确认）
  python collect_real_coverage.py --confirm --mode playmode
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

# 在 Windows 上设置控制台代码页为 UTF-8，解决中文输出乱码问题
if sys.platform == "win32":
    import ctypes as _ctypes
    try:
        _ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        _ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
import skill_config  # noqa: E402  项目相关程序集前缀/框架包标识统一从配置读取

# 项目根统一取自 skill_config：它用锚点（含 .codebuddy / .git 的目录）向上查找，
# 不依赖技能目录的固定层级。引擎改为 lib/<pack>/skills/ 分层后，固定上三级会定位到
# .codebuddy/lib 而非项目根，导致默认扫描范围与产物路径全部失配。
PROJECT_ROOT = skill_config.PROJECT_ROOT

# unity-pipeline 为**可选包**（不在 csharp.requires 内）：
#   - 已安装时技能目录经链接暴露在 .codebuddy/skills/ 下，包内再嵌套一层同名目录
#     （lib/<pack>/skills/<pack>/），故路径为 skills/unity-pipeline/unity-pipeline/scripts；
#   - 未安装时该路径不存在，本脚本**不报错**，只是无法自动轮询 Unity 测试终态，
#     由调用方改用 dotnet test 或手动确认（见 references/guide.md 规则四的分支说明）。
UNITY_WAIT = os.path.join(
    PROJECT_ROOT, ".codebuddy", "skills", "unity-pipeline", "unity-pipeline", "scripts", "unity_wait.py"
)


def unity_pipeline_available():
    """判断可选包 unity-pipeline 是否已安装（以轮询脚本存在为准）。

    用于替代硬性依赖：未安装时调用方须降级到 dotnet build / dotnet test，
    并在报告中标注「未经 unity-pipeline 校验」。
    """
    return os.path.isfile(UNITY_WAIT)

COVERAGE_SETTINGS = os.path.join(
    PROJECT_ROOT, "ProjectSettings", "Packages",
    "com.unity.testtools.codecoverage", "Settings.json",
)

# 域重载等待轮次与间隔（域重载为多轮异步过程，实测需较长等待）
DOMAIN_RELOAD_WAIT_ROUNDS = 12
DOMAIN_RELOAD_WAIT_INTERVAL = 5


def log(message):
    """输出带时间戳的进度信息。"""
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), message))


def run_unity_command(command, extra_args=None, timeout=60, check=False):
    """执行 unity command 子命令，返回 (是否成功, 标准输出)。

    返回原始文本，交由调用方解析，避免对整段 JSON 做关键字匹配。
    """
    # 0.9 起命令名为 "分组 名称"，CLI 要求整串作为单个参数传入，故不做切分
    args = ["unity", "command", command]
    if extra_args:
        args.extend(extra_args)
    try:
        result = subprocess.run(
            args, cwd=PROJECT_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        output = (result.stdout or "") + (result.stderr or "")
        success = result.returncode == 0 and "Connection reset by server" not in output
        if check and not success:
            log("命令 %s 执行异常：%s" % (command, output.strip()[:200]))
        return success, output
    except subprocess.TimeoutExpired:
        # 域重载会导致连接中断，超时属预期情况之一
        return False, "TIMEOUT"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def unity_eval(code, timeout=60):
    """执行 eval 并提取 result 字段值；解析失败返回 None。

    eval 返回形如 {"result": <值>, ...}；域重载期间会连接中断，此时返回 None。
    """
    ok, output = run_unity_command("script eval", ["--code", code], timeout=timeout)
    if not ok:
        return None
    # 从首个 { 起做增量解析，避免日志前缀干扰
    start = output.find("{")
    if start < 0:
        return None
    try:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(output[start:])
        if isinstance(obj, dict) and "result" in obj:
            return obj["result"]
        return None
    except (ValueError, TypeError):
        return None


def check_editor_via_status():
    """用 unity status 判定编辑器是否在运行（比 command 更可靠）。"""
    try:
        result = subprocess.run(
            ["unity", "status"], cwd=PROJECT_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        out = (result.stdout or "") + (result.stderr or "")
        # 输出含 ready 且含项目路径即视为运行中
        return ("ready" in out.lower()) and ("Client" in out), out.strip()[:300]
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def read_coverage_state():
    """经 eval 读取覆盖率的真实内存状态。

    返回值 dict：
      enabled        内存中的 Coverage.enabled
      chain          'REGISTERED' / 'NULL' 回调链注册状态
      assemblies     生效的程序集过滤清单程序集数
      has_framework  生效清单是否含框架包（前缀取自项目配置）
      code_opt       代码优化模式
    """
    state = {}
    # 框架包识别前缀取自项目配置，不硬编码项目名称
    framework_prefix = skill_config.framework_package_prefix()

    enabled = unity_eval("return UnityEngine.TestTools.Coverage.enabled;")
    state["enabled"] = enabled

    chain_code = (
        "var asm = System.AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault("
        "a => a.GetName().Name == \"Unity.TestTools.CodeCoverage.Editor\"); "
        "if (asm == null) return \"NO_ASM\"; "
        "var t = asm.GetType(\"UnityEditor.TestTools.CodeCoverage.CoverageReporterStarter\"); "
        "var f = t.GetField(\"CoverageReporterManager\", System.Reflection.BindingFlags.Public "
        "| System.Reflection.BindingFlags.Static); "
        "var v = f.GetValue(null); return v == null ? \"NULL\" : \"REGISTERED\";"
    )
    state["chain"] = unity_eval(chain_code)

    filter_code = (
        "var asm = System.AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault("
        "a => a.GetName().Name == \"Unity.TestTools.CodeCoverage.Editor\"); "
        "if (asm == null) return \"NO_ASM\"; "
        "var t = asm.GetType(\"UnityEditor.TestTools.CodeCoverage.CoverageReporterStarter\"); "
        "var f = t.GetField(\"CoverageReporterManager\", System.Reflection.BindingFlags.Public "
        "| System.Reflection.BindingFlags.Static); "
        "var mgr = f.GetValue(null); "
        "if (mgr == null) return \"NO_MGR\"; "
        "var rep = mgr.GetType().GetProperty(\"CoverageReporter\").GetValue(mgr); "
        "if (rep == null) return \"NO_REP\"; "
        "var filt = rep.GetType().GetMethod(\"GetReporterFilter\").Invoke(rep, null); "
        "var af = filt.GetType().GetMethod(\"GetAssemblyFiltering\").Invoke(filt, null); "
        "var inc = af.GetType().GetProperty(\"includedAssemblies\").GetValue(af) as string; "
        "return \"\" + inc.Split(',').Length + \"|\" + inc.Contains(\"%s\");"
    ) % framework_prefix
    filter_result = unity_eval(filter_code)
    if isinstance(filter_result, str) and "|" in filter_result:
        count, has_fw = filter_result.split("|", 1)
        state["assemblies"] = count
        state["has_framework"] = has_fw
    else:
        state["assemblies"] = filter_result
        state["has_framework"] = None

    state["code_opt"] = unity_eval(
        "return UnityEditor.Compilation.CompilationPipeline.codeOptimization.ToString();"
    )
    return state


def enumerate_project_assemblies():
    """枚举应纳入覆盖率的项目程序集（按配置的前缀/后缀筛选）。

    依据 P0 实测：非 batchmode 下程序集过滤从偏好读取且不展开 <all> 别名，
    故必须生成显式清单。

    前缀与后缀**均从项目配置读取**（`realCoverage.assemblyIncludePrefixes` /
    `assemblyExcludeSuffixes`），脚本不硬编码项目程序集名。
    """
    prefixes = skill_config.assembly_include_prefixes()
    suffixes = skill_config.assembly_exclude_suffixes()
    if not prefixes:
        log("警告：配置未声明 realCoverage.assemblyIncludePrefixes，无法枚举程序集")
        return []

    prefix_cond = " || ".join('n.StartsWith("%s")' % p for p in prefixes)
    exclude_cond = " && ".join('!n.EndsWith("%s")' % s for s in suffixes) if suffixes else "true"
    code = (
        "var a = System.AppDomain.CurrentDomain.GetAssemblies()"
        ".Select(x => x.GetName().Name)"
        ".Where(n => (%s) && %s)"
        ".OrderBy(x => x).ToArray(); "
        "return string.Join(\",\", a);"
    ) % (prefix_cond, exclude_cond)
    result = unity_eval(code)
    if not isinstance(result, str) or not result:
        return []
    return [name for name in result.split(",") if name]


def set_assemblies_via_window(assembly_list):
    """经 CodeCoverageWindow.AssembliesToInclude setter 写入程序集清单。

    该 setter 内部调用 CoveragePreferences.SetString -> Settings.Save，
    是唯一实测能同时更新内存缓存与磁盘文件的入口。
    """
    joined = ",".join(assembly_list)
    code = (
        "var asm = System.AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault("
        "a => a.GetName().Name == \"Unity.TestTools.CodeCoverage.Editor\"); "
        "if (asm == null) return \"NO_ASM\"; "
        "var wt = asm.GetType(\"UnityEditor.TestTools.CodeCoverage.CodeCoverageWindow\"); "
        "var w = UnityEditor.EditorWindow.GetWindow(wt, false, \"Code Coverage\", false); "
        "var prop = wt.GetProperty(\"AssembliesToInclude\", "
        "System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance); "
        "prop.SetValue(w, \"%s\"); "
        "return \"WINDOW_SET_OK\";"
    ) % joined
    return unity_eval(code)


def set_enable_via_preferences(enabled):
    """经 CoveragePreferences.SetBool 写入开关（内存缓存 + 落盘）。"""
    code = (
        "var asm = System.AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault("
        "a => a.GetName().Name == \"Unity.TestTools.CodeCoverage.Editor\"); "
        "if (asm == null) return \"NO_ASM\"; "
        "var t = asm.GetType(\"UnityEditor.TestTools.CodeCoverage.CoveragePreferences\"); "
        "var inst = t.GetProperty(\"instance\", System.Reflection.BindingFlags.Public "
        "| System.Reflection.BindingFlags.Static).GetValue(null); "
        "var sm = t.GetMethod(\"SetBool\"); var sp = sm.GetParameters(); "
        "sm.Invoke(inst, new object[] { \"EnableCodeCoverage\", %s, "
        "System.Enum.ToObject(sp[2].ParameterType, 0) }); "
        "UnityEngine.TestTools.Coverage.enabled = %s; "
        "return \"ENABLE_SET_OK\";"
    ) % ("true" if enabled else "false", "true" if enabled else "false")
    return unity_eval(code)


def trigger_domain_reload():
    """触发域重载。

    必须用 EditorUtility.RequestScriptReload()：
    实测 CompilationPipeline.RequestScriptCompilation() 不会真正重载域
    （AppDomain 哈希不变）。
    """
    code = "UnityEditor.EditorUtility.RequestScriptReload(); return \"RELOAD_REQUESTED\";"
    ok, _ = run_unity_command("script eval", ["--code", code], timeout=30)
    # 域重载会中断连接，不视为失败
    return True


def wait_for_domain_reload():
    """轮询等待域重载完成。

    域重载为多轮异步过程，期间 eval 会连接中断；以「域可稳定响应」为完成判据。
    返回最终覆盖率状态 dict。
    """
    state = None
    for round_index in range(DOMAIN_RELOAD_WAIT_ROUNDS):
        time.sleep(DOMAIN_RELOAD_WAIT_INTERVAL)
        current = read_coverage_state()
        # 域可稳定响应（enabled 读取成功）且回调链已注册即视为完成
        if current.get("enabled") is not None and current.get("chain") == "REGISTERED":
            state = current
            log("域重载已生效（第 %d 轮）" % (round_index + 1))
            break
        state = current
        log("等待域重载……第 %d/%d 轮" % (round_index + 1, DOMAIN_RELOAD_WAIT_ROUNDS))
    return state


def backup_settings():
    """备份覆盖率配置文件，返回备份路径（失败返回 None）。"""
    if not os.path.isfile(COVERAGE_SETTINGS):
        return None
    backup_dir = skill_config.resolve_artifact_dir("test_coverage.check_logs")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(
        backup_dir,
        "Settings.json.%s.bak" % datetime.now().strftime("%Y%m%d_%H%M%S"),
    )
    try:
        with open(COVERAGE_SETTINGS, "rb") as src:
            data = src.read()
        with open(backup_path, "wb") as dst:
            dst.write(data)
        return backup_path
    except OSError as exc:
        log("备份失败：%s" % exc)
        return None


def read_settings_file():
    """读取 Settings.json 的关键配置，用于与内存值对照。

    返回 dict：enable / include_count / has_framework；读取失败返回 None。
    """
    if not os.path.isfile(COVERAGE_SETTINGS):
        return None
    try:
        with open(COVERAGE_SETTINGS, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return None

    result = {"enable": None, "include_count": None, "has_framework": None}
    for item in raw.get("m_Dictionary", {}).get("m_DictionaryValues", []):
        key = item.get("key")
        try:
            inner = json.loads(item.get("value", "{}"))
        except (ValueError, TypeError):
            continue
        value = inner.get("m_Value")
        if key == "EnableCodeCoverage":
            result["enable"] = value
        elif key == "IncludeAssemblies":
            text = value or ""
            result["include_count"] = len([x for x in text.split(",") if x])
            # 框架包前缀取自项目配置，不硬编码项目名称
            prefix = skill_config.framework_package_prefix()
            result["has_framework"] = bool(prefix) and prefix in text
    return result


def restore_settings(backup_path):
    """把备份的 Settings.json 还原到原位置。

    仅还原文件；编辑器内存中的偏好需经域重载才会重新从文件读取，
    因此还原后本函数会触发一次域重载使内存与文件重新对齐。
    """
    if not backup_path or not os.path.isfile(backup_path):
        log("无可用备份，跳过还原")
        return False
    try:
        with open(backup_path, "rb") as src:
            data = src.read()
        with open(COVERAGE_SETTINGS, "wb") as dst:
            dst.write(data)
    except OSError as exc:
        log("还原失败：%s" % exc)
        return False
    log("已还原 Settings.json（来源 %s）" % os.path.basename(backup_path))
    log("提示：还原仅作用于文件；如需让内存偏好同步回原值，需再触发一次域重载")
    return True


def add_paths_to_exclude():
    """设置 PathsToExclude 为 **/Tests/**，避免测试代码进入覆盖率分母。

    与程序集清单同理，必须经 CodeCoverageWindow 的 setter
    （内部走 CoveragePreferences.SetStringForPaths -> Settings.Save）。
    """
    code = (
        "var asm = System.AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault("
        "a => a.GetName().Name == \"Unity.TestTools.CodeCoverage.Editor\"); "
        "if (asm == null) return \"NO_ASM\"; "
        "var wt = asm.GetType(\"UnityEditor.TestTools.CodeCoverage.CodeCoverageWindow\"); "
        "var w = UnityEditor.EditorWindow.GetWindow(wt, false, \"Code Coverage\", false); "
        "var prop = wt.GetProperty(\"PathsToExclude\", "
        "System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance); "
        "prop.SetValue(w, \"**/Tests/**\"); "
        "return \"EXCLUDE_SET_OK\";"
    )
    return unity_eval(code)


def run_tests(mode):
    """异步触发测试并轮询至终态，返回测试摘要文本。"""
    ok, output = run_unity_command(
        "test run", ["--mode", mode, "--async_tests", "true"], timeout=60
    )
    if not ok:
        log("test run 触发失败：%s" % output.strip()[:200])
        return None
    log("测试已启动（异步），开始轮询……")

    wait_script = UNITY_WAIT
    if not unity_pipeline_available():
        # 可选包未安装：不视为错误，降级为「无法自动轮询」，由调用方确认结果
        log("未安装可选包 unity-pipeline，跳过自动轮询与结果归一化：%s" % wait_script)
        log("请改用 dotnet test 并在报告中标注「未经 unity-pipeline 校验」")
        return None
    try:
        # 轮询脚本会把完整测试结果 JSON 打到 stdout，此处只需其退出码，
        # 故重定向到 DEVNULL，避免海量输出淹没采集进度。
        subprocess.run(
            [sys.executable, wait_script, "--command", "test status",
             "--until", "completed", "--fail-field", "status", "--fail-value", "error,cancelled"],
            cwd=PROJECT_ROOT, timeout=3600,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        log("测试轮询超时")
        return None

    summary_script = os.path.join(os.path.dirname(wait_script), "unity_test_summary.py")
    status_file = os.path.join(PROJECT_ROOT, "Temp", "pipeline_test_status.json")
    if os.path.isfile(summary_script) and os.path.isfile(status_file):
        try:
            result = subprocess.run(
                [sys.executable, summary_script, "--file", status_file],
                cwd=PROJECT_ROOT, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )
            return (result.stdout or "").strip()
        except Exception:  # noqa: BLE001
            return None
    return None


def _resolve_path(configured):
    """把配置中的产物路径解析为绝对路径（相对项目根）。

    `realCoverage.*` 是覆盖率产物的**唯一来源**，脚本不硬编码项目名、也不提供默认路径；
    配置缺失会在取值时抛出 skill_config.ConfigError。
    """
    rel = configured.strip()
    return rel if os.path.isabs(rel) else os.path.join(PROJECT_ROOT, rel)


def coverage_artifact_dirs():
    """解析报告目录与 OpenCover 目录（均取自配置，缺失即报错）。"""
    report_dir = os.path.dirname(
        _resolve_path(skill_config.get("realCoverage.reportSummaryJson"))
    )
    opencov_dir = _resolve_path(skill_config.get("realCoverage.openCoverRoot"))
    return report_dir, opencov_dir


def collect_coverage_artifacts():
    """收集覆盖率产物路径（Report/Summary.json 优先）。"""
    report_dir, opencov_dir = coverage_artifact_dirs()
    artifacts = {
        "summary_json": os.path.join(report_dir, "Summary.json"),
        "summary_xml": os.path.join(report_dir, "Summary.xml"),
        "index_html": os.path.join(report_dir, "index.htm"),
        "opencov_dir": opencov_dir,
    }
    return {key: path for key, path in artifacts.items() if os.path.exists(path)}


def print_state(label, state):
    """格式化打印覆盖率状态。"""
    if not state:
        log("%s：状态读取失败（可能仍在域重载中）" % label)
        return
    log(
        "%s：enabled=%s 回调链=%s 生效程序集=%s 含框架包=%s 代码优化=%s"
        % (
            label,
            state.get("enabled"),
            state.get("chain"),
            state.get("assemblies"),
            state.get("has_framework"),
            state.get("code_opt"),
        )
    )


def main():
    parser = argparse.ArgumentParser(
        description="Unity 真实代码覆盖率采集编排（全程不关闭编辑器）"
    )
    parser.add_argument("--confirm", action="store_true",
                        help="确认执行采集（缺省仅做前置检查与计划打印）")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅打印将执行的步骤，不做任何写入")
    parser.add_argument("--mode", default="editor", choices=["editor", "playmode"],
                        help="测试模式，默认 editor")
    parser.add_argument("--no-restore", action="store_true",
                        help="采集后不还原 Settings.json（默认会自动还原到采集前备份）")
    args = parser.parse_args()

    log("项目根目录：%s" % PROJECT_ROOT)

    # ---- 第 1 步：判定编辑器状态 ----
    running, status_text = check_editor_via_status()
    if running:
        log("情形 ①：编辑器已在运行，直接采集（不关闭编辑器）")
    else:
        log("情形 ②：编辑器未运行，需先打开")
        if args.dry_run or not args.confirm:
            log("将执行：unity open . --args \"-automated\"（后台）")
            log("等待 pipeline 就绪后继续。加 --confirm 实际执行。")
            return 0
        log("正在打开编辑器（open 会阻塞到编辑器退出，故后台执行）……")
        try:
            subprocess.Popen(
                ["unity", "open", ".", "--args", "-automated"],
                cwd=PROJECT_ROOT,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as exc:  # noqa: BLE001
            log("打开编辑器失败：%s" % exc)
            return 1
        # 等待 Pipeline 就绪
        for round_index in range(60):
            time.sleep(10)
            ready, _ = check_editor_via_status()
            if ready:
                log("编辑器已就绪（第 %d 轮）" % (round_index + 1))
                break
        else:
            log("等待编辑器就绪超时，请手动确认后重跑")
            return 1

    # ---- 第 2 步：读取当前状态（一律走 eval）----
    before = read_coverage_state()
    print_state("采集前状态", before)

    if args.dry_run:
        log("--dry-run 模式：以下为将执行的步骤，未做任何写入")
        log("  1) 备份 Settings.json")
        log("  2) 枚举项目程序集并写入 IncludeAssemblies（经 CodeCoverageWindow setter）")
        log("  3) 设置 PathsToExclude=**/Tests/**")
        log("  4) 设置 EnableCodeCoverage=true（经 CoveragePreferences.SetBool）")
        log("  5) EditorUtility.RequestScriptReload() 触发域重载并等待")
        log("  6) run_tests --mode %s --async_tests true" % args.mode)
        log("  7) 解析 CodeCoverage/Report/Summary.json")
        return 0

    if not args.confirm:
        log("尚未确认执行。请加 --confirm 参数以实际采集。")
        log("提示：采集将开启代码覆盖率并触发脚本重编译，期间不适合编辑代码。")
        return 0

    # ---- 第 3 步：备份配置 ----
    backup_path = backup_settings()
    if backup_path:
        log("已备份配置：%s" % backup_path)
    else:
        log("警告：配置备份失败，继续执行但不保证可还原")

    # ---- 第 4 步：写入配置（先写内存，再重载）----
    assemblies = enumerate_project_assemblies()
    if not assemblies:
        log("程序集枚举失败，中止采集")
        return 1
    log("枚举到 %d 个项目程序集（已排除测试程序集）" % len(assemblies))

    result = set_assemblies_via_window(assemblies)
    if result != "WINDOW_SET_OK":
        log("程序集清单写入失败：%s" % result)
        return 1
    log("程序集清单已写入内存偏好（%d 个程序集）" % len(assemblies))

    exclude_result = add_paths_to_exclude()
    log("PathsToExclude 设置：%s" % exclude_result)

    enable_result = set_enable_via_preferences(True)
    if enable_result != "ENABLE_SET_OK":
        log("覆盖率开关写入失败：%s" % enable_result)
        return 1
    log("覆盖率开关已开启（内存偏好）")

    file_state = read_settings_file()
    if file_state:
        log(
            "写入后配置文件：enable=%s 清单数=%s 含框架包=%s"
            % (file_state.get("enable"), file_state.get("include_count"),
               file_state.get("has_framework"))
        )

    # ---- 第 5 步：触发域重载并等待 ----
    log("触发域重载（EditorUtility.RequestScriptReload）……")
    trigger_domain_reload()
    after = wait_for_domain_reload()
    print_state("重载后状态", after)

    if not after or after.get("chain") != "REGISTERED":
        log("回调链未注册成功，采集中止。排查见 references/real-coverage-guide.md")
        return 1
    if after.get("has_framework") != "True":
        log("警告：生效程序集清单不含框架包，覆盖率数据可能缺失框架代码")

    # 域重载会用内存缓存回写偏好文件，此处如实对照，避免误判为已同步
    file_state = read_settings_file()
    if file_state:
        if str(file_state.get("has_framework")) != "True":
            log(
                "注意：域重载后配置文件已被内存缓存回写为 %s 个程序集（不含框架包），"
                "但生效过滤取自内存偏好，覆盖率采集不受影响"
                % file_state.get("include_count")
            )
        else:
            log("域重载后配置文件与内存一致（%s 个程序集）"
                % file_state.get("include_count"))

    # ---- 第 6 步：保活并运行测试 ----
    run_unity_command("editor set_auto_tick", ["--enable", "true"], timeout=30)
    code_opt = after.get("code_opt")
    if code_opt != "Debug":
        log("警告：代码优化为 %s，报告生成可能弹模态框阻断流程" % code_opt)

    summary = run_tests(args.mode)
    if summary:
        print(summary)
    else:
        log("测试摘要获取失败，请查看 Temp/pipeline_test_status.json")

    # ---- 第 7 步：收集产物 ----
    artifacts = collect_coverage_artifacts()
    if artifacts:
        log("覆盖率产物：")
        for key, path in artifacts.items():
            log("  %-12s %s" % (key, path))
    else:
        log("未找到覆盖率产物，请检查 CodeCoverage/ 目录是否生成")

    # ---- 第 8 步：还原配置 ----
    if args.no_restore:
        log("已指定 --no-restore，保留本次写入的覆盖率配置")
        log("  备份文件：%s" % (backup_path or "（无）"))
    else:
        restored = restore_settings(backup_path)
        if not restored:
            log("自动还原未完成，请手工还原。备份文件：%s" % (backup_path or "（无）"))
            log("  目标路径：%s" % COVERAGE_SETTINGS)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except skill_config.ConfigError as error:
        # 配置是覆盖率数据的唯一来源：配置不可用即明确报错，不静默回退默认值
        sys.stderr.write("[错误] %s\n" % error)
        sys.exit(3)
