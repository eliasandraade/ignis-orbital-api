/**
 * Contract checks for railway.ts, run in CI (npm run check). They evaluate the
 * IaC program for each environment and assert the deployment invariants that
 * protect production; `railway config plan` still has to run against the real
 * project before any apply.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { createRailwayContext, project } from "railway/iac";
import type { ResourceNode, ServiceNode } from "railway/iac";

import program, {
  API_PORT,
  BRANCHES,
  INGEST,
  INGEST_CRON,
  POSTGIS_IMAGE,
  PRODUCTION_DOMAIN,
  REGION,
  environmentOf,
  ingestJob,
} from "./railway.ts";

const root = new URL("../", import.meta.url);
const entrypoint = readFileSync(new URL("scripts/entrypoint.sh", root), "utf8");
const health = readFileSync(new URL("app/health/router.py", root), "utf8");
const ciWorkflow = readFileSync(new URL(".github/workflows/ci.yml", root), "utf8");
const alembicEnv = readFileSync(new URL("alembic/env.py", root), "utf8");

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");

async function resourcesFor(environment: string): Promise<ResourceNode[]> {
  const def = await program(createRailwayContext({ environment }), project);
  return (def.resources ?? []).flat();
}

function svc(resources: ResourceNode[], name: string): ServiceNode {
  const found = resources.find((r) => r.type === "service" && r.name === name);
  assert.ok(found, `service ${name} missing`);
  return found as ServiceNode;
}

function literal(node: ServiceNode, key: string): string | null | undefined {
  const v = node.variables?.[key];
  assert.ok(v, `${node.name}.${key} missing`);
  assert.equal(v.type, "literal", `${node.name}.${key} must be a literal`);
  return (v as { value?: string | null }).value;
}

function preserved(node: ServiceNode, key: string): void {
  assert.equal(node.variables?.[key]?.type, "preserve", `${node.name}.${key} must be preserve()`);
}

let checks = 0;
const check = (name: string, fn: () => void) => {
  fn();
  checks += 1;
  console.log(`ok - ${name}`);
};

for (const env of ["staging", "production"] as const) {
  const resources = await resourcesFor(env);
  const api = svc(resources, "ignis-api");
  const web = svc(resources, "ignis-web");
  const postgis = svc(resources, "ignis-postgis");
  const services = resources.filter((r) => r.type === "service") as ServiceNode[];
  const fromGithub = services.filter((n) => n.name !== "ignis-postgis");

  check(`${env}: resources (production ingestion exists with the cron off)`, () => {
    const expected = [
      "service.ignis-api",
      "service.ignis-postgis",
      "service.ignis-web",
      "volume.ignis-postgis-data",
      ...(INGEST[env].service ? ["service.ignis-ingest"] : []),
    ].sort();
    assert.deepEqual(resources.map((r) => r.address).sort(), expected);
    assert.equal(INGEST.production.cron, false, "production cron needs owner authorisation");
    assert.equal(INGEST.production.service, true, "production ingestion approved by the owner on 2026-11-06");
  });

  check(`${env}: deploys wait for GitHub Actions and track the environment branch`, () => {
    for (const node of fromGithub) {
      assert.equal(node.source?.checkSuites, true, `${node.name} must wait for CI`);
    }
    assert.equal(api.source?.branch, BRANCHES[env].api);
    assert.equal(web.source?.branch, BRANCHES[env].web);
    // Neither environment deploys a default or feature branch directly.
    for (const b of Object.values(BRANCHES[env])) {
      assert.ok(!["main", "master"].includes(b) && !b.startsWith("feat/"), b);
    }
    assert.deepEqual(BRANCHES.production, { api: "production", web: "production" });
  });

  check(`${env}: every service runs in the chosen region`, () => {
    for (const node of services) {
      assert.deepEqual(
        node.deploy?.multiRegionConfig,
        { [REGION]: { numReplicas: 1 } },
        `${node.name}: one replica in ${REGION}`,
      );
    }
  });

  check(`${env}: API migrates in pre-deploy (serialised), not on every replica start`, () => {
    assert.deepEqual(api.deploy?.preDeployCommand, ["/app/scripts/entrypoint.sh migrate"]);
    assert.equal(api.deploy?.startCommand, "/app/scripts/entrypoint.sh api");
    assert.equal(literal(api, "MIGRATE_ON_START"), "false");
    assert.match(entrypoint, /^\s+migrate\)$/m);
    assert.match(entrypoint, /^\s+api\)$/m);
    assert.match(alembicEnv, /pg_advisory_xact_lock/);
  });

  check(`${env}: healthchecks point to real readiness endpoints`, () => {
    assert.equal(api.deploy?.healthcheckPath, "/ready");
    assert.match(health, /@router\.get\("\/ready"\)/);
    assert.equal(web.deploy?.healthcheckPath, "/healthz");
  });

  check(`${env}: APP_ENV matches the Railway environment; no demo data`, () => {
    for (const node of services.filter((n) => n.variables?.APP_ENV)) {
      assert.equal(literal(node, "APP_ENV"), env);
    }
    assert.equal(literal(api, "ORBITAL_ALERTS_DEMO_MODE"), "false");
    assert.equal(literal(api, "SKIP_DEMO_SEED"), "true");
  });

  check(`${env}: citizens' reports (personal data) stay closed`, () => {
    assert.equal(literal(api, "PUBLIC_REPORTS_ENABLED"), "false");
  });

  check(`${env}: secrets are never literals in the repository`, () => {
    preserved(api, "JWT_SECRET_KEY");
    preserved(postgis, "POSTGRES_PASSWORD");
    for (const node of services) {
      for (const [key, value] of Object.entries(node.variables ?? {})) {
        if (/SECRET|PASSWORD|TOKEN|KEY/.test(key)) {
          assert.notEqual(value.type, "literal", `${node.name}.${key} is a literal secret`);
        }
      }
    }
  });

  check(`${env}: database and API are private; only ignis-web is public`, () => {
    assert.equal(postgis.source?.image, POSTGIS_IMAGE);
    for (const node of services.filter((n) => n.name !== "ignis-web")) {
      assert.equal(node.networking, undefined, `${node.name} must have no domain/TCP proxy`);
    }
    assert.match(ciWorkflow, new RegExp(escape(POSTGIS_IMAGE)));
    assert.match(String(literal(postgis, "DATABASE_URL")), /RAILWAY_PRIVATE_DOMAIN/);
    assert.deepEqual(api.variables?.DATABASE_URL, {
      type: "reference",
      resource: "service.ignis-postgis",
      output: "DATABASE_URL",
    });
  });

  check(`${env}: same-origin — web proxies to the API's private address`, () => {
    assert.equal(literal(web, "VITE_API_URL"), "same-origin");
    assert.equal(
      literal(web, "IGNIS_API_UPSTREAM"),
      "http://${{ignis-api.RAILWAY_PRIVATE_DOMAIN}}:${{ignis-api.PORT}}",
    );
    assert.equal(literal(api, "PORT"), API_PORT);
    assert.equal(web.variables?.VITE_USE_API, undefined);
  });

  check(`${env}: official domain only on production's ignis-web`, () => {
    const domains = JSON.stringify(web.networking ?? {});
    if (env === "production") {
      assert.match(domains, new RegExp(escape(PRODUCTION_DOMAIN)));
      assert.equal(literal(api, "CORS_ORIGINS"), `https://${PRODUCTION_DOMAIN}`);
    } else {
      assert.doesNotMatch(domains, /andradesystems/);
      assert.equal(literal(api, "CORS_ORIGINS"), "https://${{ignis-web.RAILWAY_PUBLIC_DOMAIN}}");
    }
  });

  check(`${env}: one replica, one worker (in-memory rate limit stays exact)`, () => {
    assert.equal(literal(api, "WEB_CONCURRENCY"), "1");
    assert.equal(literal(api, "TRUST_PROXY_HEADERS"), "true");
    assert.equal(literal(api, "CLIENT_IP_HEADER"), "x-real-ip");
  });

  check(`${env}: ingestion service runs one round per run, cron only when enabled`, () => {
    for (const cron of [false, true]) {
      const job = ingestJob(env, BRANCHES[env].api, "postgresql://contract-check", cron);
      assert.equal(job.deploy?.startCommand, "/app/scripts/entrypoint.sh ingest");
      assert.match(entrypoint, /^\s+ingest\)$/m);
      assert.equal(job.deploy?.cronSchedule, cron ? INGEST_CRON : undefined);
      assert.equal(job.deploy?.restartPolicyType, "NEVER");
      assert.equal(job.source?.checkSuites, true);
      assert.equal(job.source?.branch, BRANCHES[env].api);
      assert.equal(literal(job, "APP_ENV"), env);
      assert.equal(literal(job, "MIGRATE_ON_START"), "false");
      assert.equal(job.networking, undefined);
      preserved(job, "JWT_SECRET_KEY");
      assert.equal(literal(job, "INPE_QUEIMADAS_ENABLED"), "true");
      assert.equal(literal(job, "NASA_FIRMS_MAP_KEY"), undefined, "NASA FIRMS stays disabled");
    }
    assert.equal(INGEST_CRON, "*/15 * * * *");
  });
}

check("unknown/PR environments get staging settings, never production", () => {
  assert.equal(environmentOf("ignis-pr-12"), "staging");
  assert.equal(environmentOf(undefined), "staging");
  assert.equal(environmentOf("Production"), "staging");
});

check("CI runs on push to every deploy branch (required by Wait for CI)", () => {
  for (const branch of new Set(Object.values(BRANCHES).map((b) => b.api))) {
    assert.match(ciWorkflow, new RegExp(`branches: \\[[^\\]]*\\b${branch}\\b`));
  }
});

console.log(`\n${checks} checks passed`);
