import { Router, type IRouter } from "express";
import healthRouter from "./health";
import guildsRouter from "./guilds";

const router: IRouter = Router();

router.use(healthRouter);
router.use(guildsRouter);

export default router;
