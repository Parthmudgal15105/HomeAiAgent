import { createHmac, timingSafeEqual } from "node:crypto";

export const SESSION_LIFETIME_MS = 8 * 60 * 60 * 1000;

export function equal(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
}

export function createSession(secret: string, now = Date.now()): string {
  if (!secret) throw new Error("Session signing is not configured");
  const expiry = String(now + SESSION_LIFETIME_MS);
  return expiry + "." + createHmac("sha256", secret).update(expiry).digest("hex");
}

export function validSession(
  token: string | undefined,
  secret = process.env.SESSION_SECRET,
  now = Date.now(),
): boolean {
  if (!token || !secret) return false;
  const parts = token.split(".");
  if (parts.length !== 2) return false;
  const [expiry, signature] = parts;
  if (!/^\d{13}$/.test(expiry) || !/^[a-f0-9]{64}$/.test(signature)) return false;
  const expiresAt = Number(expiry);
  if (!Number.isSafeInteger(expiresAt) || expiresAt <= now) return false;
  return equal(signature, createHmac("sha256", secret).update(expiry).digest("hex"));
}

export function allowedOrigin(origin: string | null, requestOrigin: string, configuredOrigin?: string): boolean {
  return Boolean(origin && (origin === requestOrigin || origin === configuredOrigin));
}
