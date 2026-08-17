import type { APIRoute } from "astro";
import { evaluateRule } from "../../../lib/calendar-rule";
import { generateIcs } from "../../../lib/ics";
import { allFristTasks, fristPath, yearsFor } from "../../../lib/tasks";
import type { Deadline } from "../../../lib/deadline-plan";

// One file per year of a Frist the statute fixes by itself. A Frist counted
// from the visitor's own date has no fixed day, so it gets no feed here.
export function getStaticPaths() {
  return allFristTasks().flatMap(({ task }) =>
    yearsFor(task).map((year) => ({
      params: { path: `${task.id}/${year}` },
      props: { task, year },
    })),
  );
}

export const GET: APIRoute = ({ props, site }) => {
  const { task, year } = props as { task: Deadline; year: number };
  const hit = evaluateRule(task.rule!, year, "DE");
  if (!hit) return new Response("Not found", { status: 404 });

  const ics = generateIcs(
    [
      {
        uid: `${task.id}-${year}@wannometer.de`,
        from: hit.date,
        to: hit.date,
        title: `${task.label} (${year})`,
        description: [task.source_label, task.note].filter(Boolean).join(" - "),
        url: new URL(`/${fristPath(task.id, year)}/`, site).href,
        alarmDays: 3,
      },
    ],
    `${task.label} ${year}`,
  );
  return new Response(ics, {
    headers: {
      "Content-Type": "text/calendar; charset=utf-8",
      "Content-Disposition": `attachment; filename="${task.id}-${year}.ics"`,
    },
  });
};
