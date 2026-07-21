// Flat, unified view of every browsable item on the site, for the homepage's
// single tag-searchable card grid. Every category now flows through
// lib/pages.ts's one model, so this is one gathering step instead of four.
import { getAllPages, getCategoryMeta, getPagesInCategory } from "./pages";

export interface ContentCard {
  title: string;
  description: string;
  url: string;
  type: string;
  category: string;
  tags: string[];
  featured: boolean;
}

// Shown by default within its type's cluster on the homepage; non-featured
// items stay collapsed behind a "show more" toggle until the user expands or
// searches/filters. A category-size threshold (not a category-specific rule -
// Feiertage just happens to be the one category large enough to hit it today)
// keeps any future large category from dumping hundreds of cards onto the
// homepage by default.
const FEATURED_CATEGORY_MAX_SIZE = 20;

export function getAllContent(): ContentCard[] {
  return getAllPages().map((p) => {
    const categoryName = getCategoryMeta(p.category).name;
    return {
      title: p.meta.title,
      description: p.meta.description,
      url: `/${p.category}/${p.slug}/`,
      type: categoryName,
      category: p.category,
      tags: [categoryName, ...p.meta.tags],
      featured: p.meta.featured ?? false
    };
  });
}
