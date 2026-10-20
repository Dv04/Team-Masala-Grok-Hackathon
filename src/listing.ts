/** Product fields every listing_live event must carry, filled from the upstream design/product event. */
export interface ListingProduct {
  title: string;
  description: string;
  image: string;
  url: string;
  sku: string;
  id: string;
  price_usd: number;
  product_type?: string;
  tagline?: string;
  cost_usd?: number;
  trend?: string;
}

function record(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : undefined;
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function priceOf(value: unknown, fallback: unknown): number {
  const picked = typeof value === "number" ? value : typeof fallback === "number" ? fallback : Number(value ?? fallback);
  return Number.isFinite(picked) ? picked : 0;
}

export function listingFromUpstream(input: {
  taskId: string;
  output?: Record<string, unknown>;
  summary?: string;
}): { product: ListingProduct; copy: string } {
  const output = input.output ?? {};
  const raw = record(output.product) ?? record(output);
  const nested = raw ?? {};
  const title = text(nested.title) || text(output.product) || text(input.summary) || "Pulse Studio";
  const description = text(nested.description) || text(nested.tagline) || text(output.tagline) || `${title} is ready for buyers.`;
  const url = text(output.url) || text(nested.url) || text(nested.image_url) || "/pulse";
  const image = text(nested.image_url) || text(output.image_url) || text(nested.image) || url;
  const id = text(nested.id) || text(nested.sku) || input.taskId;
  const sku = text(nested.sku) || id;
  const product: ListingProduct = {
    title,
    description,
    image,
    url,
    sku,
    id,
    price_usd: priceOf(nested.price_usd, output.price),
  };
  const productType = text(nested.product_type);
  const tagline = text(nested.tagline);
  const trend = text(nested.trend);
  if (productType) product.product_type = productType;
  if (tagline) product.tagline = tagline;
  if (typeof nested.cost_usd === "number") product.cost_usd = nested.cost_usd;
  if (trend) product.trend = trend;
  const copy = `${title} is live. ${description}`.replace(/\s+/g, " ").trim();
  return { product, copy };
}
