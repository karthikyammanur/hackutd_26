import { EVIDENCE_PREFIX, handleEvidenceProxy, type EvidenceEnv } from "./evidence-proxy";
import type { Ledger } from "./ledger";
import type { ProxyLedger } from "./ledger-do";
import { handleProxy, PREFIX, type ProxyEnv } from "./proxy";
import { handleTLife, TLIFE_PREFIX, type TLifeEnv } from "./tlife";

export { ProxyLedger } from "./ledger-do";

interface Env extends ProxyEnv, EvidenceEnv, TLifeEnv {
  ASSETS: { fetch(request: Request): Promise<Response> };
  LEDGER: DurableObjectNamespace<ProxyLedger>;
}

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);
    if (pathname === PREFIX || pathname.startsWith(`${PREFIX}/`)) {
      const ledger = env.LEDGER.get(env.LEDGER.idFromName("site")) as unknown as Ledger;
      return handleProxy(request, env, ledger);
    }
    if (pathname === EVIDENCE_PREFIX || pathname.startsWith(`${EVIDENCE_PREFIX}/`)) {
      return handleEvidenceProxy(request, env);
    }
    if (pathname.startsWith(`${TLIFE_PREFIX}/`)) return handleTLife(request, env);
    return env.ASSETS.fetch(request);
  },
};
