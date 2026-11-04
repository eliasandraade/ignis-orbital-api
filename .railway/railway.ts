/**
 * IGNIS Orbital on Railway — Infrastructure as Code (railway/iac).
 *
 * Project "IGNIS Orbital" with two isolated environments, each with its own
 * PostGIS volume, credentials and variables (docs/IGNIS/RAILWAY-DEPLOYMENT.md):
 *
 *   ignis-web      public   nginx + SPA; same-origin proxy of /api/v1, /health,
 *                           /ready to ignis-api over the private network
 *   ignis-api      private  FastAPI; no public domain, migrates in pre-deploy
 *   ignis-postgis  private  PostgreSQL 16 + PostGIS 3.4, persistent volume
 *   ignis-ingest   private  one ingestion round per run (cron), staging only
 *
 *   staging     ← branch `staging` of both repositories (fast-forwarded by a
 *                 person from a reviewed branch; see BRANCHES)
 *   production  ← branch `production`, moved only by promote.yml (fast-forward
 *                 to a commit of the default branch that passed CI)
 *
 * Every deploy waits for the repository's GitHub Actions (checkSuites). Secrets
 * are never in this file: `preserve()` keeps the value set once per environment
 * in Railway. A missing secret makes the service refuse to start.
 *
 * Read-only preview:  cd .railway && npm ci && railway link && railway config plan
 */
import { defineRailway, github, image, preserve, service, volume } from "railway/iac";
import type { ResourceNode, ServiceNode, VariableValue } from "railway/iac";

export type IgnisEnvironment = "staging" | "production";

export const REPOSITORIES = {
  api: "eliasandraade/ignis-orbital-api",
  web: "eliasandraade/ignis-fire-watch",
} as const;

/**
 * Branch each environment deploys from. `staging` is a deploy branch: a person
 * fast-forwards it (never force) to the commit to homologate — today the head
 * of feat/ignis-admin-cockpit, while the PR stack is not merged; afterwards the
 * default branch. Production never follows a default or feature branch.
 */
export const BRANCHES: Record<IgnisEnvironment, { api: string; web: string }> = {
  staging: { api: "staging", web: "staging" },
  production: { api: "production", web: "production" },
};

/** Lowest latency to Ceará among Railway's regions (none in South America). */
export const REGION = "us-east4-eqdc4a";

/** Official address, served by ignis-web in production only. */
export const PRODUCTION_DOMAIN = "ignis.andradesystems.com.br";

/** Same major versions as CI and docker-compose (PostgreSQL 16 + PostGIS 3.4). */
export const POSTGIS_IMAGE = "postgis/postgis:16-3.4";

/**
 * Cluster directory inside the volume. Staging uses `pgdata-2`: its first
 * cluster (`pgdata`) was copied while running during the volume's region
 * migration (europe-west4 → us-east4, 2026-11-04, before any migration or
 * data) and arrived without the `ignis` database. It is left in place, not
 * deleted (RAILWAY-PROVISIONING-REPORT.md). Never change a value that holds data.
 */
export const PGDATA_DIR: Record<IgnisEnvironment, string> = {
  staging: "pgdata-2",
  production: "pgdata",
};

/** Port the API listens on; referenced by ignis-web's private upstream. */
export const API_PORT = "8000";

/**
 * Orbital ingestion (NASA FIRMS + INPE), entrypoint role `ingest`.
 *  - service: exists in the environment (a deploy runs one round, then exits);
 *  - cron:    re-runs every 15 minutes.
 * Staging: service first (manual round validated), cron after. Production: off
 * until the owner authorises it after staging homologation.
 */
export const INGEST: Record<IgnisEnvironment, { service: boolean; cron: boolean }> = {
  staging: { service: true, cron: false },
  production: { service: false, cron: false },
};
export const INGEST_CRON = "*/15 * * * *";

export function environmentOf(name: string | undefined): IgnisEnvironment {
  if (name === "production") return "production";
  if (name === "staging") return "staging";
  // PR environments and anything unexpected get staging settings, never production's.
  return "staging";
}

/** Browser origins allowed by the API (same-origin needs none; kept explicit). */
export function corsOrigins(env: IgnisEnvironment): string {
  return env === "production"
    ? `https://${PRODUCTION_DOMAIN}`
    : "https://${{ignis-web.RAILWAY_PUBLIC_DOMAIN}}";
}

export default defineRailway((ctx, project) => {
  const env = environmentOf(ctx.environment);
  const branch = BRANCHES[env];

  // --- database: private network only, no TCP proxy, no public URL ---------------
  const pgData = volume("ignis-postgis-data", {
    region: REGION,
    sizeMB: env === "production" ? 10240 : 5120,
  });
  const postgis = service("ignis-postgis", {
    source: image(POSTGIS_IMAGE),
    volumeMounts: { "/var/lib/postgresql/data": pgData },
    // Region and replica count (multiRegionConfig); the volume follows the service.
    replicas: { [REGION]: 1 },
    deploy: { restartPolicyType: "ALWAYS" },
    env: {
      POSTGRES_USER: "ignis",
      POSTGRES_DB: "ignis",
      // Hex value (URL-safe) set once per environment, sealed.
      POSTGRES_PASSWORD: preserve(),
      // The volume root holds lost+found; initdb needs an empty directory.
      PGDATA: `/var/lib/postgresql/data/${PGDATA_DIR[env]}`,
      DATABASE_URL:
        "postgresql://${{POSTGRES_USER}}:${{POSTGRES_PASSWORD}}@${{RAILWAY_PRIVATE_DOMAIN}}:5432/${{POSTGRES_DB}}",
    },
  });

  // --- API: FastAPI image from the repository Dockerfile, private only ------------
  const api = service("ignis-api", {
    source: github(REPOSITORIES.api, { branch: branch.api, checkSuites: true }),
    build: {
      builder: "DOCKERFILE",
      dockerfilePath: "Dockerfile",
      // Documentation-only changes do not redeploy.
      watchPatterns: [
        "app/**",
        "alembic/**",
        "seed/**",
        "scripts/**",
        "data/reference/**",
        "Dockerfile",
        "requirements.lock",
        "alembic.ini",
      ],
    },
    // Rate limits and caches are in memory, per process: one replica and one
    // worker keep them exact (ADMIN-SECURITY-REVIEW §10).
    replicas: { [REGION]: 1 },
    deploy: {
      startCommand: "/app/scripts/entrypoint.sh api",
      // Once per deploy, before the new version receives traffic; failure aborts
      // the deploy. Concurrent runs serialise on an advisory lock (alembic/env.py).
      preDeployCommand: ["/app/scripts/entrypoint.sh migrate"],
      preDeployTimeoutSeconds: 600,
      // /ready checks the database: a version that cannot reach it never goes live.
      healthcheckPath: "/ready",
      healthcheckTimeout: 120,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 5,
    },
    env: {
      APP_ENV: env,
      PORT: API_PORT,
      DATABASE_URL: postgis.env.DATABASE_URL,
      JWT_SECRET_KEY: preserve(),
      CORS_ORIGINS: corsOrigins(env),
      ORBITAL_ALERTS_DEMO_MODE: "false",
      INPE_QUEIMADAS_ENABLED: "true",
      MIGRATE_ON_START: "false",
      SKIP_DEMO_SEED: "true",
      WEB_CONCURRENCY: "1",
      // Only ignis-web reaches the API (private network); it forwards the
      // X-Real-IP that Railway's edge wrote for the client.
      TRUST_PROXY_HEADERS: "true",
      CLIENT_IP_HEADER: "x-real-ip",
      FORWARDED_ALLOW_IPS: "*",
    },
  });

  // --- web: React/Vite build served by unprivileged nginx --------------------------
  const web = service("ignis-web", {
    source: github(REPOSITORIES.web, { branch: branch.web, checkSuites: true }),
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    replicas: { [REGION]: 1 },
    deploy: {
      healthcheckPath: "/healthz",
      healthcheckTimeout: 30,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 5,
    },
    ...(env === "production" ? { domains: [PRODUCTION_DOMAIN] } : {}),
    env: {
      // Build arg: relative API URLs, CSP connect-src 'self'.
      VITE_API_URL: "same-origin",
      // Runtime: nginx proxies /api/v1, /health and /ready here.
      IGNIS_API_UPSTREAM: "http://${{ignis-api.RAILWAY_PRIVATE_DOMAIN}}:${{ignis-api.PORT}}",
    },
  });

  const resources: ResourceNode[] = [pgData, postgis, api, web];

  if (INGEST[env].service) {
    resources.push(ingestJob(env, branch.api, postgis.env.DATABASE_URL, INGEST[env].cron));
  }

  return project("IGNIS Orbital", { environments: ["staging", "production"], resources });
});

/**
 * The ingestion service, built from the API image. One round per run; with
 * `cron` Railway starts it every 15 minutes. Exported for the contract check.
 */
export function ingestJob(
  env: IgnisEnvironment,
  apiBranch: string,
  databaseUrl: string | VariableValue,
  cron: boolean,
): ServiceNode {
  return service("ignis-ingest", {
    source: github(REPOSITORIES.api, { branch: apiBranch, checkSuites: true }),
    build: {
      builder: "DOCKERFILE",
      dockerfilePath: "Dockerfile",
      watchPatterns: ["app/**", "Dockerfile", "requirements.lock"],
    },
    replicas: { [REGION]: 1 },
    deploy: {
      startCommand: "/app/scripts/entrypoint.sh ingest",
      // One round per execution; each round re-reads the last 26 h, and
      // deduplication makes the overlap free. A round times out at 13 min.
      ...(cron ? { cronSchedule: INGEST_CRON } : {}),
      restartPolicyType: "NEVER",
    },
    env: {
      APP_ENV: env,
      DATABASE_URL: databaseUrl,
      JWT_SECRET_KEY: preserve(),
      // NASA FIRMS stays disabled until a real key is set and homologated.
      INPE_QUEIMADAS_ENABLED: "true",
      CORS_ORIGINS: corsOrigins(env),
      MIGRATE_ON_START: "false",
      SKIP_DEMO_SEED: "true",
    },
  });
}
