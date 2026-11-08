const PUSH_SERVICES = /^https:\/\/(fcm\.googleapis\.com|updates\.push\.services\.mozilla\.com|[a-z0-9.-]+\.push\.apple\.com|[a-z0-9.-]+\.notify\.windows\.com)\//;

/** Only real push services, so a subscription can't make this Worker call an arbitrary address. */
export function isPushEndpoint(endpoint: string): boolean {
  return endpoint.length <= 1024 && PUSH_SERVICES.test(endpoint);
}
