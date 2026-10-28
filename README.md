# MCP Contract Test Generator Agent

An LLM-powered automation tool that generates, executes, and validates contract tests for MCP (Model Context Protocol) tools. 

## 🎯 Overview
When integrating new tools via MCP, manually writing contract tests (valid params, invalid params, permission checks) is time-consuming and error-prone. This project builds a minimal automated loop to generate tests and validate MCP tool contracts, ensuring tools behave exactly as defined.

## 🛡️ Core Design: Dual Failure Classification
The most critical part of the agent is **preventing the LLM from "cheating" to pass tests**. It implements a strict dual classification logic:
- **`test_error`**: The generated test itself is wrong (e.g., missing imports, syntax errors). The agent automatically feeds the error back to the LLM to fix the test (capped at 3 rounds).
- **`tool_bug`**: The test is correct according to the contract, but the tool implementation returns invalid data (e.g., returning a string `'10'` instead of integer `10`). The agent **stops immediately, preserves the test, and flags a bug**. It **never** weakens assertions just to pass.
- **Contract Coverage**: Outputs a field-level coverage report (explicitly distinguished from code branch coverage).

## 🚀 Features & Evidence
- **Real LLM Verified**: Successfully called DeepSeek API to generate 9 valid test cases that passed in the first round.
- **Bug Detection**: Injected a flaw (returning `'10'`) and successfully triggered the `tool_bug` stop logic (1 failed, 8 passed).
- **Isolated Execution**: Uses `subprocess` with a 30s timeout to execute tests, protecting the main process.
- **AST Validation**: Validates LLM-generated code before writing to the filesystem.

## 🛠️ Quick Start
1. Set environment variables (e.g., DeepSeek):
   ```bash
   export LLM_API_KEY="your_api_key"
   export LLM_BASE_URL="https://api.deepseek.com"
   export LLM_MODEL="deepseek-flash"
