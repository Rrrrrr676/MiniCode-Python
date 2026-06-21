import type { TimelineItem, ToolActivity } from "../../api/types";

export interface ToolGroupItem {
  id: string;
  kind: "tool-group";
  name: string;
  seq: number;
  turnId: string;
  toolIds: string[];
}

export type PresentationalTimelineItem = TimelineItem | ToolGroupItem;

function isStableTool(item: TimelineItem, tools: Record<string, ToolActivity>) {
  return item.kind === "tool" && tools[item.toolId]?.status !== "running";
}

export function groupTimelineTools(
  timeline: TimelineItem[],
  tools: Record<string, ToolActivity>,
): PresentationalTimelineItem[] {
  const result: PresentationalTimelineItem[] = [];
  let index = 0;

  while (index < timeline.length) {
    const item = timeline[index];
    if (!isStableTool(item, tools) || item.kind !== "tool") {
      result.push(item);
      index += 1;
      continue;
    }

    const tool = tools[item.toolId];
    const groupItems = [item];
    let cursor = index + 1;
    while (cursor < timeline.length) {
      const candidate = timeline[cursor];
      if (
        candidate.kind !== "tool"
        || !isStableTool(candidate, tools)
        || candidate.turnId !== item.turnId
        || tools[candidate.toolId]?.name !== tool.name
      ) break;
      groupItems.push(candidate);
      cursor += 1;
    }

    if (groupItems.length === 1) {
      result.push(item);
    } else {
      result.push({
        id: `tool-group-${item.turnId}-${tool.name}-${item.seq}`,
        kind: "tool-group",
        name: tool.name,
        seq: item.seq,
        turnId: item.turnId,
        toolIds: groupItems.map((entry) => entry.toolId),
      });
    }
    index = cursor;
  }

  return result;
}
