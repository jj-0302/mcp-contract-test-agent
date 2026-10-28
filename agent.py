"""Single-agent, bounded contract test generation loop."""
import ast
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import argparse
import contextlib
import hashlib
from datetime import datetime, timezone

import llm_client

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
TEST_PATH = OUTPUT / "generated_tests" / "test_contract.py"


def extract_code(llm_response):
    """Extract one unambiguous Python block, then validate before writing."""
    blocks = re.findall(r"```(?:python|py)?[ \t]*\r?\n(.*?)```", llm_response, re.S | re.I)
    if len(blocks) > 1:
        raise ValueError("多个代码块，无法确定唯一测试模块")
    code = (blocks[0] if blocks else llm_response).strip()
    ast.parse(code)
    if not code:
        raise ValueError("提取结果为空")
    return code


def checked_response(raw):
    print("LLM 原始返回前 500 字符:\n" + raw[:500])
    try:
        code = extract_code(raw)
    except (SyntaxError, ValueError) as exc:
        print(f"extract_code: 失败；{type(exc).__name__}: {exc}")
        raise
    print("extract_code: 成功；ast.parse: 通过")
    return code


def extract_schema(tool_def):
    for key, expected in (("tool_name", str), ("parameters", dict),
                          ("returns", dict), ("permission", str)):
        if not isinstance(tool_def.get(key), expected):
            raise ValueError(f"工具定义缺少或包含无效字段: {key}")
    for name, spec in tool_def["parameters"].items():
        if not isinstance(spec, dict) or "type" not in spec:
            raise ValueError(f"参数定义无效: {name}")
    return copy.deepcopy(tool_def)


def generate_tests(schema, permission_rules):
    prompt = (ROOT / "prompts/generate_test.txt").read_text(encoding="utf-8")
    raw = llm_client.call_llm(prompt + "\n" + json.dumps(
        {"schema": schema, "permission_rules": permission_rules}, ensure_ascii=False))
    content = checked_response(raw)
    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEST_PATH.write_text(content + "\n", encoding="utf-8")
    return content


def run_pytest(test_path):
    env = os.environ.copy()
    # Do not pass API credentials to generated tests.
    env.pop("LLM_API_KEY", None)
    env["PYTHONPATH"] = str(ROOT)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTHONOPTIMIZE", None)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(Path(test_path).resolve()),
             "-c", str(ROOT / "pytest.ini"), "-p", "no:cacheprovider", "-q", "--tb=short", "-rA"],
            cwd=ROOT, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        def decode(value):
            return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
        return 124, decode(exc.stdout), decode(exc.stderr) + "\npytest timeout=30"


def classify_failure(stdout, schema=None):
    # Conservative heuristics, never claim to prove an implementation defect.
    match = re.search(r'assert isinstance\(result\[[\x27\"](\w+)[\x27\"]\], (int|bool|str|list)\)', stdout)
    declared = {"integer": "int", "boolean": "bool", "string": "str", "array": "list"}
    expected = declared.get((schema or {}).get("returns", {}).get(match[1])) if match else None
    if match and expected and re.search(r"^E\s+(?:AssertionError: )?assert False", stdout, re.M):
        if match[2] == expected:
            result, reason = "tool_bug", f"失败断言要求 {match[1]} 为 {expected}，与工具定义契约一致；pytest 展示实际返回值类型不符，疑似工具 bug"
        else:
            result, reason = "test_error", f"断言要求 {match[2]}，契约要求 {expected}，测试断言与定义不一致；禁止自动改断言"
    elif "CONTRACT_RETURN_MISMATCH" in stdout:
        result, reason = "tool_bug", "受控契约断言直接读取工具定义；实际返回类型不符合定义，疑似工具 bug"
    elif any(s in stdout for s in ("SyntaxError", "IndentationError", "ImportError", "ModuleNotFoundError")):
        result, reason = "test_error", "语法或导入错误；不是工具返回值违约证据"
    elif re.search(r"NameError: name '(pytest|invoke_tool)' is not defined", stdout):
        result, reason = "test_error", "缺少已知测试依赖导入，可尝试仅补充导入"
    else:
        result, reason = "unknown", "证据不足，停止自动修正，需人工复核"
    print(f"分类: {result}；依据: {reason}")
    return result


def safe_import_repair(original, candidate):
    """Only append known imports; preserve every original AST node in order."""
    try:
        before, after = ast.parse(original), ast.parse(candidate)
    except SyntaxError:
        return False
    allowed = {ast.dump(ast.parse(s).body[0]) for s in
               ("import pytest", "from tool_adapter import invoke_tool")}
    old = [ast.dump(node) for node in before.body]
    new = [ast.dump(node) for node in after.body]
    index = 0
    additions = []
    for node in new:
        if index < len(old) and node == old[index]:
            index += 1
        elif node in allowed:
            additions.append(node)
        else:
            return False
    return index == len(old) and bool(additions) and len(set(additions)) == len(additions)


def print_contract_coverage(schema, test_content):
    covered = {"parameters": set(), "returns": set(), "permission": set()}
    try:
        tree = ast.parse(test_content)
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                continue
            # Read explicit tags, not incidental field names in comments or strings.
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call) or ast.unparse(deco.func) != "pytest.mark.contract":
                    continue
                for kw in deco.keywords:
                    if kw.arg not in covered:
                        continue
                    try:
                        value = ast.literal_eval(kw.value)
                    except (ValueError, TypeError):
                        continue
                    values = [value] if isinstance(value, str) else value
                    if isinstance(values, (tuple, list)):
                        covered[kw.arg].update(v for v in values if isinstance(v, str))
    except SyntaxError:
        pass
    def entries(names, group):
        return " / ".join(f"{name} {'✅' if name in covered[group] else '❌'}" for name in names)
    report = "\n".join([
        "参数覆盖：" + entries(schema["parameters"], "parameters"),
        "返回字段覆盖：" + entries(schema["returns"], "returns"),
        "权限用例：有权限 " + ("✅" if "allowed" in covered["permission"] else "❌")
        + " / 无权限 " + ("✅" if "denied" in covered["permission"] else "❌"),
        "注意：以上为契约字段覆盖，不是代码分支覆盖率",
        "清单依据测试函数的显式 contract 标签静态提取；不代表执行通过或证明断言充分。",
    ])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "coverage_report.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    return report


def run_agent(tool_def_path, max_rounds=3, test_file=None):
    if type(max_rounds) is not int or not 1 <= max_rounds <= 3:
        raise ValueError("max_rounds 必须为 1 到 3（包含首次执行）")
    path = Path(tool_def_path)
    if not path.is_absolute():
        path = ROOT / path
    schema = extract_schema(json.loads(path.read_text(encoding="utf-8")))
    if test_file:
        print(f"测试来源：复用现有文件 {test_file}；本轮不调用 LLM")
        content = extract_code(Path(test_file).read_text(encoding="utf-8"))
        TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        TEST_PATH.write_text(content + "\n", encoding="utf-8")
    else:
        content = generate_tests(schema, schema["permission"])
    history = []
    status = "未收敛"
    for round_no in range(1, max_rounds + 1):
        code, stdout, stderr = run_pytest(TEST_PATH)
        print(f"第 {round_no}/{max_rounds} 轮；pytest returncode={code}\n{stdout}{stderr}")
        entry = {"round": round_no, "returncode": code, "stdout": stdout, "stderr": stderr}
        history.append(entry)
        if code == 0:
            print("分类: 不适用；依据: pytest 通过，无失败")
            status = "通过"
            break
        failure = classify_failure(stdout + "\n" + stderr, schema)
        entry["classification"] = failure
        if failure != "test_error":
            status = "疑似工具 bug，停止修正" if failure == "tool_bug" else "unknown，停止修正"
            break
        if round_no == max_rounds:
            break
        candidate = checked_response(llm_client.call_llm(
            "修正 pytest 缺失导入。只输出完整 Python 代码。仅允许补充 import pytest 或 "
            "from tool_adapter import invoke_tool。保留其他所有语句、断言和装饰器，不得放宽断言。\n"
            + "测试代码：\n" + content + "\n失败输出：\n" + stdout + stderr))
        if not safe_import_repair(content, candidate):
            status = "未收敛：修正超出补充导入范围，已拒绝并保留原测试"
            break
        content = candidate
        TEST_PATH.write_text(content + "\n", encoding="utf-8")
    print_contract_coverage(schema, content)
    result = {"status": status, "rounds": history}
    (OUTPUT / "run_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("运行结果：" + status + f"；共 {len(history)} 轮")
    if len(history) < 2:
        print("修正后第二次运行：未执行（首次通过或已停止）")
    return result


def run_evidence(kind, implementation=None, test_file=None):
    global TEST_PATH
    OUTPUT.mkdir(parents=True, exist_ok=True)
    TEST_PATH = OUTPUT / "generated_tests" / ("test_tool_bug.py" if kind == "bug" else "test_contract.py")
    log = OUTPUT / ("run_log_tool_bug.txt" if kind == "bug" else "run_log_real_llm.txt")
    previous = os.environ.get("MCP_TOOL_IMPLEMENTATION")
    if implementation:
        os.environ["MCP_TOOL_IMPLEMENTATION"] = str(Path(implementation).resolve())
    else:
        os.environ.pop("MCP_TOOL_IMPLEMENTATION", None)
    with log.open("w", encoding="utf-8") as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        print("时间: " + datetime.now(timezone.utc).isoformat())
        print(f"证据任务: {kind}；实现: {implementation or '本地正常示例'}")
        try:
            result = run_agent("input/tool_def.json", test_file=test_file)
            if kind == "bug":
                original = extract_code(Path(test_file).read_text(encoding="utf-8")) if test_file else None
                unchanged = original is not None and TEST_PATH.read_text(encoding="utf-8") == original + "\n"
                print(f"测试保留: {unchanged}；SHA256: {hashlib.sha256(TEST_PATH.read_bytes()).hexdigest()}")
                print("停止行为: " + result["status"])
            if kind == "real" and result["status"] == "通过" and len(result["rounds"]) == 1:
                print("手动构造的解析负例（不是 LLM 返回）：解释文字 + markdown + 缺冒号")
                try:
                    checked_response("说明\n```python\ndef test_syntax()\n    assert True\n```\n结束")
                except SyntaxError as exc:
                    classify_failure(f"SyntaxError: {exc}")
                    print("语法负例：正确拒绝，未写入测试文件，未执行 pytest")
        except (RuntimeError, ValueError, OSError, SyntaxError) as exc:
            print(f"错误: {type(exc).__name__}: {exc}")
            category = classify_failure(f"{type(exc).__name__}: {exc}")
            print("LLM 原始返回: 若请求失败则无返回；extract_code: 未完成")
            print("pytest 第一次 returncode: N/A（生成阶段失败）；第二次运行: 未执行")
            print("最终结果：未通过；共 0 轮 pytest；未降级为模拟。语法错误需人工修复以保留断言。")
            result = {"status": "未通过", "error": str(exc), "classification": category, "rounds": []}
        finally:
            if previous is None:
                os.environ.pop("MCP_TOOL_IMPLEMENTATION", None)
            else:
                os.environ["MCP_TOOL_IMPLEMENTATION"] = previous
        (OUTPUT / f"result_{kind}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(log.read_text(encoding="utf-8"))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", choices=["real", "bug"], default="real")
    parser.add_argument("--implementation")
    parser.add_argument("--test-file")
    args = parser.parse_args()
    outcome = run_evidence(args.evidence, args.implementation, args.test_file)
    sys.exit(0 if outcome["status"] == "通过" else 1)
