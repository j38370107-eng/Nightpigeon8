import express, { type Express } from "express";
import cors from "cors";
import pinoHttp from "pino-http";
import path from "node:path";
import router from "./routes";
import { logger } from "./lib/logger";

const app: Express = express();

app.use(
  pinoHttp({
    logger,
    serializers: {
      req(req) {
        return { id: req.id, method: req.method, url: req.url?.split("?")[0] };
      },
      res(res) {
        return { statusCode: res.statusCode };
      },
    },
  }),
);
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

const publicDir = path.join(__dirname, "..", "public");

app.use("/api", express.static(publicDir));

app.get("/api/dashboard", (_req, res) => {
  res.sendFile(path.join(publicDir, "dashboard.html"));
});
app.get("/api/dashboard/:id", (_req, res) => {
  res.sendFile(path.join(publicDir, "config.html"));
});

app.use("/api", router);

export default app;
