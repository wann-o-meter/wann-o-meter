import { describe, expect, it } from "vitest";
import { homepageQuestions } from "./homepage-questions";

describe("homepageQuestions", () => {
  it("fills the saisonkalender template with a real produce season, dropping the trailing e", () => {
    expect(homepageQuestions()).toContain("Wann ist Erdbeersaison?");
  });

  it("fills the schulferien/feiertage/urlaubsfenster templates with a real Bundesland name", () => {
    const questions = homepageQuestions();
    expect(questions).toContain("Wann sind Schulferien in Bayern?");
    expect(questions).toContain("Wann ist der nächste Feiertag in Bayern?");
    expect(questions).toContain("Wann lohnt sich ein Brückentag in Bayern?");
  });

  it("never mentions a non-German country (Feiertage's 200+ other countries are out of scope)", () => {
    for (const q of homepageQuestions()) expect(q).not.toContain("Feiertag in USA");
  });
});
