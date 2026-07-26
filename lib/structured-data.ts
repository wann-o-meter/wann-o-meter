// Shared schema.org JSON-LD builders (PLAN.md's "one source of truth" spirit
// applied to structured data too). Plain object builders, not a schema
// library - the vocabulary needed here is small and stable: Event,
// BreadcrumbList, Dataset, WebSite. Render with:
//   <script type="application/ld+json" set:html={JSON.stringify(graph([...]))} />

export function graph(nodes: object[]): object {
  return { "@context": "https://schema.org", "@graph": nodes };
}

export interface EventLocation {
  name: string; // place name, e.g. "Nordrhein-Westfalen"
  addressRegion?: string; // omitted when the place IS the country
  addressCountry: string; // ISO 3166-1 alpha-2
}

export interface EventInput {
  name: string;
  startDate: string; // ISO date
  endDate?: string; // ISO date, omitted from output when same as startDate
  url?: string;
  description?: string;
  image?: string;
  location: EventLocation;
}

// Deliberately no `eventStatus`/`organizer`/`performer`/`eventAttendanceMode`
// - those would have to be fabricated (a holiday or bridge-day window has no
// status, host, or performer), and inventing values is worse than omitting
// them. `location` is required (with an `address`, which Google counts as a
// required property too - a Place with only a `name` is reported as invalid
// in Search Console): a page with no real region gets no Event nodes rather
// than an invented venue. Entries stay ineligible for Google's Event
// rich-result carousel (which isn't the target here anyway) but are valid,
// extractable structured data for answer engines that just want typed
// name/date facts.
export function eventNode(e: EventInput): object {
  return {
    "@type": "Event",
    name: e.name,
    startDate: e.startDate,
    ...(e.endDate && e.endDate !== e.startDate ? { endDate: e.endDate } : {}),
    ...(e.url ? { url: e.url } : {}),
    ...(e.description ? { description: e.description } : {}),
    ...(e.image ? { image: e.image } : {}),
    location: {
      "@type": "Place",
      name: e.location.name,
      address: {
        "@type": "PostalAddress",
        ...(e.location.addressRegion ? { addressRegion: e.location.addressRegion } : {}),
        addressCountry: e.location.addressCountry,
      },
    },
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
// for a crawler, AI or otherwise. `license`/`creator` are constant, not
// per-call input - every Dataset node here is the site's own aggregated
// export of /data, which is CC BY 4.0 in its entirety (see data/LICENSE),
// regardless of what a given window's own `source.license` says about its
// upstream origin.
export function datasetNode(input: DatasetInput): object {
  return {
    "@type": "Dataset",
    name: input.name,
    description: input.description,
    url: input.url,
    license: "https://creativecommons.org/licenses/by/4.0/",
    creator: { "@type": "Organization", name: "Wann-O-Meter", url: "https://wannometer.de" },
    distribution: input.distributions.map((d) => ({
      "@type": "DataDownload",
      contentUrl: d.url,
      encodingFormat: d.encodingFormat,
    })),
  };
}

export interface FaqInput {
  question: string;
  answer: string;
}

// Every Q&A passed here MUST also be visible in the rendered HTML (see
// src/pages/[...path].astro's year view, which renders the same list it feeds
// this). FAQ markup whose content a user cannot find on the page is a Google
// structured-data violation, not just an unused enhancement - so this builder
// is deliberately dumb: it never invents or reformats a question, it only types
// what the page already shows.
export function faqNode(items: FaqInput[]): object {
  return {
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: { "@type": "Answer", text: item.answer },
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
