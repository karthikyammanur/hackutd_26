// The small part of the Workers runtime types this Worker uses.
declare module "cloudflare:workers" {
  export abstract class DurableObject<Env = unknown> {
    constructor(ctx: DurableObjectState, env: Env);
    protected ctx: DurableObjectState;
    protected env: Env;
  }
}

interface SqlStorage {
  exec(query: string, ...bindings: (string | number | null)[]): { toArray(): Record<string, unknown>[] };
}

interface DurableObjectState {
  storage: { sql: SqlStorage };
}

interface DurableObjectNamespace<T = unknown> {
  idFromName(name: string): unknown;
  get(id: unknown): T;
}
