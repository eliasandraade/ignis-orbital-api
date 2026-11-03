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

import program, { BRANCHES, POSTGIS_IMAGE, environmentOf } from "./railway.ts";

const root = new URL("../", import.meta.url);
const entrypoint = readFileSync(new URL("scripts/entrypoint.sh", root), "utf8");
const health = readFileSync(new URL("app/health/router.py", root), "utf8");
const ciWorkflow = readFileSync(new URL(".github/workflows/ci.yml", root), "utf8");

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
  const api = svc(resources, "api");
  const web = svc(resources, "web");
  const postgis = svc(resources, "postgis");

  check(`${env}: only api, web, postgis and its volume (Phase 1 job off)`, () => {
    assert.deepEqual(resources.map((r) => r.address).sort(), [
      "service.api",
      "service.postgis",
      "service.web",
      "volume.postgis-data",
    ]);
  });

  check(`${env}: deploys wait for GitHub Actions and track the environment branch`, () => {
    for (const [node, expected] of [
      [api, BRANCHES[env].api],
      [web, BRANCHES[env].web],
    ] as const) {
      assert.equal(node.source?.checkSuites, true, `${node.name} must wait for CI`);
      assert.equal(node.source?.branch, expected);
    }
    if (env === "production") {
      // A merge to a default branch must never reach production.
      assert.ok(!["main", "master"].includes(api.source?.branch ?? ""));
      assert.ok(!["main", "master"].includes(web.source?.branch ?? ""));
    }
  });

  check(`${env}: API migrates in pre-deploy, not on every replica start`, () => {
    assert.deepEqual(api.deploy?.preDeployCommand, ["/app/scripts/entrypoint.sh migrate"]);
    assert.equal(api.deploy?.startCommand, "/app/scripts/entrypoint.sh api");
    assert.equal(literal(api, "MIGRATE_ON_START"), "false");
    assert.match(entrypoint, /^\s+migrate\)$/m);
    assert.match(entrypoint, /^\s+api\)$/m);
  });

  check(`${env}: healthchecks point to real readiness endpoints`, () => {
    assert.equal(api.deploy?.healthcheckPath, "/ready");
    assert.match(health, /@router\.get\("\/ready"\)/);
    assert.equal(web.deploy?.healthcheckPath, "/healthz");
  });

  check(`${env}: APP_ENV matches the Railway environment`, () => {
    assert.equal(literal(api, "APP_ENV"), env);
  });

  check(`${env}: secrets are never literals in the repository`, () => {
    preserved(api, "JWT_SECRET_KEY");
    preserved(api, "NASA_FIRMS_MAP_KEY");
    preserved(postgis, "POSTGRES_PASSWORD");
    for (const node of [api, web, postgis]) {
      for (const [key, value] of Object.entries(node.variables ?? {})) {
        if (/SECRET|PASSWORD|TOKEN|KEY/.test(key)) {
          assert.notEqual(value.type, "literal", `${node.name}.${key} is a literal secret`);
        }
      }
    }
  });

  check(`${env}: database is private (no domain, no TCP proxy) and pinned to CI's PostGIS`, () => {
    assert.equal(postgis.source?.image, POSTGIS_IMAGE);
    assert.equal(postgis.networking, undefined);
    assert.match(ciWorkflow, new RegExp(POSTGIS_IMAGE.replace(/[.]/g, "\\.")));
    assert.match(String(literal(postgis, "DATABASE_URL")), /RAILWAY_PRIVATE_DOMAIN/);
    assert.deepEqual(api.variables?.DATABASE_URL, {
      type: "reference",
      resource: "service.postgis",
      output: "DATABASE_URL",
    });
  });

  check(`${env}: CORS and API URL are HTTPS Railway domains of this environment`, () => {
    assert.equal(literal(api, "CORS_ORIGINS"), "https://${{web.RAILWAY_PUBLIC_DOMAIN}}");
    assert.equal(literal(web, "VITE_API_URL"), "https://${{api.RAILWAY_PUBLIC_DOMAIN}}");
    assert.equal(literal(web, "VITE_USE_API"), "true");
    assert.equal(literal(api, "ORBITAL_ALERTS_DEMO_MODE"), "false");
  });

  check(`${env}: client IP comes from Railway's X-Real-IP`, () => {
    assert.equal(literal(api, "TRUST_PROXY_HEADERS"), "true");
    assert.equal(literal(api, "CLIENT_IP_HEADER"), "x-real-ip");
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
