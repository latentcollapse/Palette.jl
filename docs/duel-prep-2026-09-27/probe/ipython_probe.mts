// Runs the polyglot build script through Prime-Agent-Control's real IPython tool (no model call).
import { copyFileSync, mkdtempSync, mkdirSync } from "node:fs";
import { join } from "node:path";
const C = "/mnt/d/Code Projects/Project NIRA/The Battleground/Prime-Agent-Control/packages/coding-agent/src/core";
const { AuthStorage } = await import(`${C}/auth-storage.js`);
const { ModelRegistry } = await import(`${C}/model-registry.js`);
const { DefaultResourceLoader } = await import(`${C}/resource-loader.js`);
const { createAgentSession } = await import(`${C}/sdk.js`);
const { SessionManager } = await import(`${C}/session-manager.js`);
const { SettingsManager } = await import(`${C}/settings-manager.js`);
const root = `${process.env.PROBE_ROOT}`;
const cwd = mkdtempSync(join(root, "ipy-ws-")); const agentDir = mkdtempSync(join(root, "ipy-agent-"));
mkdirSync(join(agentDir, "rlm"));
copyFileSync(join(root, "build_script.sh"), join(cwd, "build_script.sh"));
const authStorage = AuthStorage.inMemory(); authStorage.setRuntimeApiKey("local-llamacpp", "local");
const modelRegistry = ModelRegistry.create(authStorage);
const settingsManager = SettingsManager.create(cwd, agentDir);
const resourceLoader = new DefaultResourceLoader({ cwd, agentDir, settingsManager }); await resourceLoader.reload();
const model: any = { id: "probe", name: "probe", api: "openai-completions", provider: "local-llamacpp", baseUrl: "http://127.0.0.1:9/v1",
	reasoning: false, input: ["text"], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, contextWindow: 16384, maxTokens: 2048 };
const { session } = await createAgentSession({ cwd, agentDir, authStorage, modelRegistry, settingsManager, resourceLoader, model,
	sessionManager: SessionManager.inMemory(cwd), initialActiveToolNames: ["ipython"], allowedToolNames: ["ipython"],
	ipythonExecutionTimeoutMs: 600000, rlmSessionDir: join(agentDir, "rlm") });
const tool: any = session.getToolDefinition("ipython");
const code = `import subprocess, os, getpass
print("PATH=" + os.environ["PATH"][:160]); print("HOME=" + os.environ.get("HOME", "")); print("user=" + getpass.getuser())
r = subprocess.run(["bash", "build_script.sh"], capture_output=True, text=True)
print(r.stdout[-1500:]); print("STDERR:", r.stderr[-1200:]); print("exit", r.returncode)`;
const res = await tool.execute("probe-1", { code }, undefined, undefined, undefined);
console.log(res.content.map((c: any) => c.text).join("\n"));
await session.disposeAsync?.();
process.exit(0);
