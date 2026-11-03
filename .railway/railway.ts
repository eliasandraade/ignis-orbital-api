/**
 * IGNIS on Railway — Infrastructure as Code (railway/iac).
 *
 * One Railway project ("ignis") with two isolated environments, each with its
 * own PostGIS volume, credentials and variables:
 *
 *   staging     api ← ignis-orbital-api@main      web ← ignis-fire-watch@master
 *   production  api ← ignis-orbital-api@production web ← ignis-fire-watch@production
 *
 * Merging to a default branch can only reach staging. Production changes only
 * when someone promotes a reviewed commit to the protected `production`
 * branch. Every deploy waits for the repository's GitHub Actions (checkSuites)
 * and the API migrates in its pre-deploy step before any new replica starts.
 *
 * Secrets are never in this file: `preserve()` keeps the sealed value set once
 * per environment in Railway (docs/IGNIS/RAILWAY-DEPLOYMENT.md §4). A missing
 * secret makes the service refuse to start instead of falling back to a default.
 *
 * Read-only preview:  cd .railway && npm ci && railway link && railway config plan
 */
import { defineRailway, github, image, preserve, service, volume } from "railway/iac";
import type { ResourceNode } from "railway/iac";

export type IgnisEnvironment = "staging" | "production";

export const REPOSITORIES = {
  api: "eliasandraade/ignis-orbital-api",
  web: "eliasandraade/ignis-fire-watch",
} as const;

/** Branch each environment deploys from (see BRANCH-STRATEGY in both repos). */
export const BRANCHES: Record<IgnisEnvironment, { api: string; web: string }> = {
  staging: { api: "main", web: "master" },
  production: { api: "production", web: "production" },
};

/** Same major versions as CI and docker-compose (PostgreSQL 16 + PostGIS 3.4). */
export const POSTGIS_IMAGE = "postgis/postgis:16-3.4";

/**
 * Phase 1 (docs/IGNIS/PHASE-1-BACKLOG.md): scheduled FIRMS ingestion. Stays
 * off until the job exists in the API image; a cron service pointing to a
 * missing command would fail every 15 minutes.
 */
export const ENABLE_FIRMS_INGEST_JOB = false;

export function environmentOf(name: string | undefined): IgnisEnvironment {
  if (name === "production") return "production";
  if (name === "staging") return "staging";
  // PR environments and anything unexpected get staging settings, never production's.
  return "staging";
}

export default defineRailway((ctx, project) => {
  const env = environmentOf(ctx.environment);
  const branch = BRANCHES[env];

  // --- database: private network only, no TCP proxy, no public URL ---------------
  const pgData = volume("postgis-data", { sizeMB: env === "production" ? 10240 : 5120 });
  const postgis = service("postgis", {
    source: image(POSTGIS_IMAGE),
    volumeMounts: { "/var/lib/postgresql/data": pgData },
    deploy: { restartPolicyType: "ALWAYS" },
    env: {
      POSTGRES_USER: "ignis",
      POSTGRES_DB: "ignis",
      // Hex value (URL-safe) set once per environment, sealed.
      POSTGRES_PASSWORD: preserve(),
      // The volume root holds lost+found; initdb needs an empty directory.
      PGDATA: "/var/lib/postgresql/data/pgdata",
      DATABASE_URL:
        "postgresql://${{POSTGRES_USER}}:${{POSTGRES_PASSWORD}}@${{RAILWAY_PRIVATE_DOMAIN}}:5432/${{POSTGRES_DB}}",
    },
  });

  // --- API: FastAPI image from the repository Dockerfile --------------------------
  const api = service("api", {
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
        "Dockerfile",
        "requirements.lock",
        "alembic.ini",
      ],
    },
    deploy: {
      startCommand: "/app/scripts/entrypoint.sh api",
      // Once per deploy, before the new version receives traffic; failure aborts the deploy.
      preDeployCommand: ["/app/scripts/entrypoint.sh migrate"],
      preDeployTimeoutSeconds: 600,
      // /ready checks the database: a version that cannot reach it never goes live.
      healthcheckPath: "/ready",
      healthcheckTimeout: 120,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 5,
      // In-memory rate limits and FIRMS cache are per process (SECURITY-REVIEW §6).
      numReplicas: 1,
    },
    env: {
      APP_ENV: env,
      DATABASE_URL: postgis.env.DATABASE_URL,
      JWT_SECRET_KEY: preserve(),
      NASA_FIRMS_MAP_KEY: preserve(),
      CORS_ORIGINS: "https://${{web.RAILWAY_PUBLIC_DOMAIN}}",
      ORBITAL_ALERTS_DEMO_MODE: "false",
      MIGRATE_ON_START: "false",
      WEB_CONCURRENCY: "2",
      // Railway's edge overwrites X-Real-IP; the container is reachable only through it.
      TRUST_PROXY_HEADERS: "true",
      CLIENT_IP_HEADER: "x-real-ip",
      FORWARDED_ALLOW_IPS: "*",
    },
  });

  // --- web: React/Vite build served by unprivileged nginx --------------------------
  const web = service("web", {
    source: github(REPOSITORIES.web, { branch: branch.web, checkSuites: true }),
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    deploy: {
      healthcheckPath: "/healthz",
      healthcheckTimeout: 30,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 5,
      numReplicas: 1,
    },
    // Vite inlines these at build time (Dockerfile ARGs); the API origin also
    // feeds the Content-Security-Policy connect-src.
    env: {
      VITE_USE_API: "true",
      VITE_API_URL: "https://${{api.RAILWAY_PUBLIC_DOMAIN}}",
    },
  });

  const resources: ResourceNode[] = [pgData, postgis, api, web];

  if (ENABLE_FIRMS_INGEST_JOB) {
    resources.push(
      service("firms-ingest", {
        source: github(REPOSITORIES.api, { branch: branch.api, checkSuites: true }),
        build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
        deploy: {
          startCommand: "/app/scripts/entrypoint.sh firms-ingest",
          // FIRMS NRT updates roughly every 3 h per satellite; 15 min keeps latency low
          // while the job itself skips windows it already persisted.
          cronSchedule: "*/15 * * * *",
          restartPolicyType: "NEVER",
        },
        env: {
          APP_ENV: env,
          DATABASE_URL: postgis.env.DATABASE_URL,
          JWT_SECRET_KEY: preserve(),
          NASA_FIRMS_MAP_KEY: preserve(),
          CORS_ORIGINS: "https://${{web.RAILWAY_PUBLIC_DOMAIN}}",
          MIGRATE_ON_START: "false",
        },
      }),
    );
  }

  return project("ignis", { environments: ["staging", "production"], resources });
});
