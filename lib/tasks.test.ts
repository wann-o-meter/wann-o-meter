import { describe, expect, it } from "vitest";
import { allFristTasks, fristPath, yearsFor } from "./tasks";

const tasks = allFristTasks();
const byId = new Map(tasks.map((t) => [t.task.id, t]));

describe("allFristTasks", () => {
  // Reclassifying a task as soft silently deletes its page, so the list is
  // spelled out rather than counted.
  it("gives every task that carries a statutory basis", () => {
    expect([...byId.keys()].sort()).toEqual(
      [
        "arbeitsuchend-melden",
        "elterngeld-beantragen",
        "geburtsanzeige-standesamt",
        "internetanbieter-kuendigen-ummelden",
        "kfz-ummeldung",
        "kindergeld-beantragen",
        "kuendigungsfrist-pruefen",
        "rundfunkbeitrag",
        "steuererklaerung-abgeben",
        "ummeldung-einwohnermeldeamt",
        "wohnung-kuendigen",
      ].sort(),
    );
  });

  it("keeps no soft task and gives each a direction", () => {
    for (const { task } of tasks) {
      expect(task.kind).not.toBe("soft");
      expect(task.direction).toBeDefined();
      expect(task.source_url).toBeTruthy();
    }
  });

  it("knows which plan a task came from", () => {
    expect(byId.get("wohnung-kuendigen")?.vorhaben?.slug).toBe("umzug");
    // Nothing bundles the Steuererklärung yet, so it stands alone.
    expect(byId.get("steuererklaerung-abgeben")?.vorhaben).toBeUndefined();
  });
});

describe("yearsFor", () => {
  it("gives year pages only where the answer moves", () => {
    expect(yearsFor(byId.get("wohnung-kuendigen")!.task)).toEqual([]);
    const years = yearsFor(byId.get("steuererklaerung-abgeben")!.task);
    expect(years[0]).toBe(2024); // first_year of the rule
    expect(years.length).toBeGreaterThan(1);
  });
});

describe("fristPath", () => {
  it("builds the canonical path, with and without a year", () => {
    expect(fristPath("wohnung-kuendigen")).toBe("frist/wohnung-kuendigen");
    expect(fristPath("steuererklaerung-abgeben", 2026)).toBe(
      "frist/steuererklaerung-abgeben/2026",
    );
  });
});
