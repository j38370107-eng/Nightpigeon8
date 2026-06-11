import { Router, type IRouter } from "express";
import { readFile, writeFile, mkdir, access } from "node:fs/promises";
import path from "node:path";

const router: IRouter = Router();

const WORKSPACE_ROOT = path.join(__dirname, "..", "..", "..");
const DATA_DIR = path.join(WORKSPACE_ROOT, "bot", "data");
const GUILDS_FILE = path.join(DATA_DIR, "guilds.json");
const CONFIGS_DIR = path.join(DATA_DIR, "configs");

async function fileExists(p: string): Promise<boolean> {
  try { await access(p); return true; } catch { return false; }
}

router.get("/guilds", async (_req, res) => {
  try {
    if (!(await fileExists(GUILDS_FILE))) {
      return res.json([]);
    }
    const raw = await readFile(GUILDS_FILE, "utf-8");
    res.json(JSON.parse(raw));
  } catch {
    res.status(500).json({ error: "Failed to read guild list" });
  }
});

router.get("/guilds/:id/config", async (req, res) => {
  const { id } = req.params;
  if (!/^\d+$/.test(id)) return res.status(400).json({ error: "Invalid guild ID" });
  const configPath = path.join(CONFIGS_DIR, `${id}.yaml`);
  try {
    if (!(await fileExists(configPath))) {
      return res.json({ config: "" });
    }
    const raw = await readFile(configPath, "utf-8");
    res.json({ config: raw });
  } catch {
    res.status(500).json({ error: "Failed to read config" });
  }
});

router.post("/guilds/:id/config", async (req, res) => {
  const { id } = req.params;
  if (!/^\d+$/.test(id)) return res.status(400).json({ error: "Invalid guild ID" });
  const { config } = req.body as { config?: string };
  if (typeof config !== "string") return res.status(400).json({ error: "config must be a string" });
  try {
    await mkdir(CONFIGS_DIR, { recursive: true });
    await writeFile(path.join(CONFIGS_DIR, `${id}.yaml`), config, "utf-8");
    res.json({ ok: true });
  } catch {
    res.status(500).json({ error: "Failed to save config" });
  }
});

export default router;
