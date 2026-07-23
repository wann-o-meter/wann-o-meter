import { describe, expect, it } from "vitest";
import { homepageQuestions } from "./homepage-questions";

describe("homepageQuestions", () => {
  const texts = () => homepageQuestions().map((q) => q.text);

  it("fills the saisonkalender template with a real produce season, dropping the trailing e", () => {
    expect(texts()).toContain("Wann ist Erdbeersaison?");
  });

  it("fills the schulferien/feiertage/urlaubsfenster templates with a real Bundesland name", () => {
    expect(texts()).toContain("Wann sind Schulferien in Bayern?");
    expect(texts()).toContain("Wann ist der nächste Feiertag in Bayern?");
    expect(texts()).toContain("Wann lohnt sich ein Brückentag in Bayern?");
  });

  it("never mentions a non-German country (Feiertage's 200+ other countries are out of scope)", () => {
    for (const t of texts()) expect(t).not.toContain("Feiertag in USA");
  });

  it("pairs each question with the calendar layer id(s) it's actually about", () => {
    const questions = homepageQuestions();
    expect(questions).toContainEqual({
      text: "Wann ist Erdbeersaison?",
      before: "Wann ist ",
      emphasis: "Erdbeersaison?",
      after: "",
      layerIds: ["saisonkalender--erdbeere"],
    });
  });

  // The trailing "?" is part of the emphasized span (not left plain in
  // `after`) - typeset in the same italic serif as the rest of the clause
  // instead of snapping back to the page's sans right at the sentence end.
  it("splits the emphasized clause without the generic 'Wann ist/sind...' opener, question mark included", () => {
    const question = homepageQuestions().find((q) => q.text === "Wann sind Schulferien und Feiertage in Mecklenburg-Vorpommern?");
    expect(question).toMatchObject({
      before: "Wann sind ",
      emphasis: "Schulferien und Feiertage in Mecklenburg-Vorpommern?",
      after: "",
      layerIds: ["feiertage--de-mv", "schulferien--mv"],
    });
  });
});
