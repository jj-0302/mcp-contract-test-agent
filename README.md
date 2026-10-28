# MCP 契约测试生成 Agent

## 项目边界说明

输入为示例或构造的工具定义，不代表完整真实工具契约。已在真实 DeepSeek LLM 和故意有 bug 的本地工具实现上验证，实际记录见下文；没有连接生产 MCP 服务。不替代团队测试体系，只补新工具接入时容易漏的契约用例。契约字段覆盖 ≠ 代码分支覆盖率。

参考 Pear Agent 的 MCP 契约测试基础，实现最小的“生成→执行→失败分类→修正→契约覆盖”链路。纯 Python 单 Agent 固定循环，无 UI、无复杂框架。

输入是示例工具定义，不代表完整真实工具契约。`tool_adapter.py` 是本地演示实现，不连接 MCP 服务、不执行库存同步。更换 JSON 后，需要自行接入真实工具适配器并更新提示词中的异常约定。示例额外约定：MMDD 是有效月日（允许 0229），缺必填/枚举/格式错误抛 ValueError，类型错误抛 TypeError，无权限抛 PermissionError。返回的库存数量没有业务含义。

## 运行（PowerShell）

```powershell
cd 'D:\ai test\mcp_test_agent'
python -m pip install pytest openai
$env:LLM_API_KEY = '你的密钥'
$env:LLM_BASE_URL = 'https://api.openai.com/v1'
$env:LLM_MODEL = 'gpt-4o-mini'
python agent.py
```

BASE_URL 可替换成兼容 Chat Completions 的服务地址，需包含 `/v1`（若服务要求）。MODEL 按服务支持情况设置。客户端用标准库发送兼容请求，不依赖 OpenAI SDK；上面保留任务指定的安装命令。没有 API key 会明确报错，不会回退到假 LLM。

输出：`output/generated_tests/test_contract.py`、`output/coverage_report.txt`、`output/run_result.json`（状态、各轮退出码、输出及分类）。相对输入路径以项目目录为基准。失败返回非零退出码。

## 修正边界

最多 3 轮，按任务 Step4b 将首次执行计入轮数，所以最多执行 3 次、修正 2 次；max_rounds 只接受 1–3。最后一轮仍失败标记“未收敛”。只有已知缺失导入的 NameError 被视为可自动修正的测试错误。LLM 修正结果经过 AST 检查，只允许补充 `import pytest` 或 `from tool_adapter import invoke_tool`，其余语句必须完全保留。

不自动放宽断言；tool_bug 立即停止，不修改测试。语法检查在写入文件和执行 pytest 之前完成。语法错误分类为 test_error，但当前不自动修复语法（无法以 AST 保证原断言不变），记录失败并要求人工处理。

## 失败分类判断规则

- test_error：语法错误、导入错误、断言与契约定义不一致（测试写错）。识别到不一致不意味着允许修改断言；自动修正仍只允许补充已知导入。
- tool_bug：测试断言与工具定义一致，但实际返回值不符合契约。当前能核对 pytest 输出中的 `isinstance(result[字段], 类型)` 与 schema 返回类型，并检查失败输出；独立契约测试另提供明确的返回类型违约标记。
- unknown：无法判断时停止并人工介入。普通 AssertionError、DID NOT RAISE 或业务值断言不自动认定为工具 bug。规则只覆盖受支持的断言形式，不能分析所有 Python 测试。

契约字段覆盖 ≠ 代码分支覆盖率。清单只读取测试函数的 `pytest.mark.contract` 参数/返回字段/权限标签，✅ 表示存在声明用例，不表示执行成功、断言充分或真实业务正确。没有标签不会因注释提到字段而算覆盖。

pytest 使用 `subprocess.run(timeout=30)`。这是进程隔离，不是安全沙箱；生成代码拥有当前用户的文件和网络访问权限，只在可信环境运行。传给子进程的环境移除了 LLM_API_KEY。

## 离线自检

```powershell
python -m pytest test_agent.py -q
```

自检替换 LLM 为固定响应，不需要 key，不会访问 API；修正和 bug 场景实际执行 pytest 子进程，临时输出不会覆盖正常运行结果。

- 缺少 pytest 导入 → LLM 补充导入 → 实际 pytest 通过。
- 无充分契约依据的错误断言 → unknown → 保留原测试，停止调用 LLM。
- 三轮失败 → 未收敛（该边界测试模拟失败流）。
- 拒绝修改断言、删测试、加入跳过逻辑的修正。
- 超时返回、unknown 停止、无 key 报错、静态覆盖清单。

离线单元测试使用 Mock，仅验证流程边界；以下两份证据日志不使用模拟 LLM。

本次回归自检：14 passed in 1.58s，记录为 `output/self_check.txt`。默认临时目录曾有权限错误，最终使用项目 `output` 下独立临时目录完成检查。

## 复现证据包

```powershell
# 仅需首次配置，在本机隐藏输入新密钥；不要将密钥发到聊天里
powershell -NoProfile -ExecutionPolicy Bypass -File .\configure.ps1
# 从当前用户环境变量读配置，依次运行真实调用与故障实现
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_evidence.ps1
```

脚本使用 `https://api.deepseek.com/chat/completions` 和 `deepseek-flash`，本次已经实际调用成功。普通 `python agent.py` 读取当前进程环境；用户级变量通过上面的脚本加载。不会访问 Codex 内部接口，不记录密钥。缺 key、HTTP 错误、超时均明确报错，不静默降级。

两份固定日志为 `output/run_log_real_llm.txt` 和 `output/run_log_tool_bug.txt`；结构化结果分别为 `output/result_real.json` 和 `output/result_bug.json`。生成的原测试为 `output/generated_tests/test_contract.py`；故障执行保留副本为 `test_tool_bug.py`。日志会在复跑时更新。

正常真实运行通过后，bug 任务复用同一份 LLM 生成代码，仅替换被测实现路径。若真实调用失败，脚本明确使用 `examples/test_bug_contract.py` 人工独立测试验证 bug，不把它当作 LLM 生成结果。故障实现的非零退出码是预期证据，不表示工具测试通过。

## 运行记录

2026-10-28 的实际运行。以下为两份日志的关键摘录，共 15 行（省略完整 pytest 清单）：

```text
LLM 请求地址: https://api.deepseek.com/chat/completions；模型: deepseek-flash
LLM 原始返回前 500 字符:
import pytest
from tool_adapter import invoke_tool
extract_code: 成功；ast.parse: 通过
第 1/3 轮；pytest returncode=0
9 passed in 0.04s
运行结果：通过；共 1 轮
extract_code: 失败；SyntaxError: expected ':' (<unknown>, line 1)
分类: test_error；依据: 语法或导入错误；不是工具返回值违约证据
    assert isinstance(result["synced_count"], int)
E    +  where False = isinstance('10', int)
1 failed, 8 passed in 0.06s
分类: tool_bug；依据: 失败断言要求 synced_count 为 int，与工具定义契约一致；pytest 展示实际返回值类型不符，疑似工具 bug
停止行为: 疑似工具 bug，停止修正
```

真实 LLM 首轮通过，因此没有第二次修正运行；日志明确记为未执行。SyntaxError 来自任务要求的手动构造 Markdown 负例，不是服务返回。bug 失败测试为 `test_sync_inventory_valid_parameters_returns_expected_fields`：期望 int，实际 `'10'` 为 str。原测试保留检查为 True，SHA256 为 `de2ea26dde70ca0a2dd35ea27c42f62c8e06158fadb6019275f8c55697bcf982`。

`output/coverage_report.txt` 实际样例：

```text
参数覆盖：date ✅ / store ✅
返回字段覆盖：success ✅ / synced_count ✅ / errors ✅
权限用例：有权限 ✅ / 无权限 ✅
```

以上为契约字段覆盖，不是代码分支覆盖率。标签仅表示存在声明的测试，不表示所有测试通过。

```text
提取 schema → 真实 LLM 生成测试 → extract_code → ast.parse 语法检查
                 │ API 失败                         │ 语法错误
                 └→ 记录未通过，不降级              └→ test_error，保留断言，人工处理
                                                    │ 通过
                                              写文件 → 执行 pytest（30 秒）
                                                        ├→ 通过
                                                        └→ 失败分类
                                                            ├→ test_error
                                                            │   ├→ 缺导入 → LLM 修正 → AST 检查 → 重跑
                                                            │   └→ 超范围修正/达到 3 轮 → 未收敛停止
                                                            ├→ tool_bug → 保留测试，停止修正
                                                            └→ unknown → 停止，人工介入
                                有测试内容的运行结束 → 契约覆盖清单及运行日志
```
