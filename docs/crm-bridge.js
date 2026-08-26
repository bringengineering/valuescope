(function initBringValueScopeBridge(global) {
  "use strict";

  const VERSION = 1;
  const MAX_STRING_BYTES = 1_024;
  const encoder = new TextEncoder();
  const PAGE_NAMES = new Set(["wonju", "sales", "valueup", "system"]);
  const RECORD_KEYS = new Set([
    "externalId", "name", "address", "lat", "lng", "category", "summary",
  ]);

  function boundedString(value, required) {
    if (typeof value !== "string") return required ? null : "";
    const normalized = value.trim();
    if (required && !normalized) return null;
    if (encoder.encode(normalized).byteLength > MAX_STRING_BYTES) return null;
    return normalized;
  }

  function sanitize(page, record) {
    if (!PAGE_NAMES.has(page) || !record || typeof record !== "object" || Array.isArray(record)) return null;
    if (Object.keys(record).some((key) => !RECORD_KEYS.has(key))) return null;
    const externalId = boundedString(record.externalId, true);
    const name = boundedString(record.name, true);
    const address = boundedString(record.address, false);
    const category = boundedString(record.category, false);
    const summary = boundedString(record.summary, false);
    if (externalId === null || name === null || address === null || category === null || summary === null) return null;

    const lat = record.lat == null ? null : Number(record.lat);
    const lng = record.lng == null ? null : Number(record.lng);
    if (lat !== null && (!Number.isFinite(lat) || lat < 37 || lat > 38)) return null;
    if (lng !== null && (!Number.isFinite(lng) || lng < 127 || lng > 129)) return null;

    return Object.freeze({
      "sourcePage": page,
      "externalId": externalId,
      "name": name,
      "address": address,
      "lat": lat,
      "lng": lng,
      "category": category,
      "summary": summary,
    });
  }

  function send(envelope) {
    window.parent.postMessage(envelope, "*");
    return true;
  }

  global.BringValueScope = Object.freeze({
    ready(page) {
      if (!PAGE_NAMES.has(page)) return false;
      return send(Object.freeze({ type: "BRING_VALUESCOPE_READY", version: VERSION, page }));
    },
    select(page, record) {
      const safe = sanitize(page, record);
      if (!safe) return false;
      return send(Object.freeze({ type: "BRING_VALUESCOPE_SELECTION", version: VERSION, record: safe }));
    },
  });
})(window);
