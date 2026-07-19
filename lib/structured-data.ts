// Shared schema.org JSON-LD builders (PLAN.md's "one source of truth" spirit
// applied to structured data too). Plain object builders, not a schema
// library - the vocabulary needed here is small and stable: Event,
// BreadcrumbList, Dataset, WebSite. Render with:
//   <script type="application/ld+json" set:html={JSON.stringify(graph([...]))} />

export function graph(nodes: object[]): object {
  return { "@context": "https://schema.org", "@graph": nodes };
}

export interface EventInput {
  name: string;
  startDate: string; // ISO date
  endDate?: string; // ISO date, omitted from output when same as startDate
  url?: string;
}

// Deliberately no `location`/`eventStatus`/`eventAttendanceMode` - those
// would have to be fabricated (a holiday or bridge-day window has no venue),
// and inventing values is worse than omitting them. This keeps entries
// ineligible for Google's Event rich-result carousel (which isn't the
// target here anyway) but still valid, extractable structured data for
// answer engines that just want typed name/date facts.
export function eventNode(e: EventInput): object {
  return {
    "@type": "Event",
    name: e.name,
    startDate: e.startDate,
    ...(e.endDate && e.endDate !== e.startDate ? { endDate: e.endDate } : {}),
    ...(e.url ? { url: e.url } : {}),
  };
}

export interface BreadcrumbInput {
  name: string;
  url: string;
}

export function breadcrumbNode(items: BreadcrumbInput[]): object {
  return {
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: item.name,
      item: item.url,
    })),
  };
}

export interface DatasetInput {
  name: string;
  description: string;
  url: string;
  distributions: { url: string; encodingFormat: "application/json" | "text/calendar" }[];
}

// One DataDownload per machine-readable format this page offers (JSON/ICS) -
// the single most direct "don't scrape the HTML, fetch this instead" signal
// for a crawler, AI or otherwise.
export function datasetNode(input: DatasetInput): object {
  return {
    "@type": "Dataset",
    name: input.name,
    description: input.description,
    url: input.url,
    distribution: input.distributions.map((d) => ({
      "@type": "DataDownload",
      contentUrl: d.url,
      encodingFormat: d.encodingFormat,
    })),
  };
}

export interface WebSiteInput {
  name: string;
  url: string;
  description: string;
}

export function websiteNode(input: WebSiteInput): object {
  return {
    "@type": "WebSite",
    name: input.name,
    url: input.url,
    description: input.description,
  };
}
