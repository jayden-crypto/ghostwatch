/**
 * Turns the flat, ordinal-sorted step list of a trace (contract §6) into the rows of the trace
 * tree. Pure functions: no React, no clock.
 */
import type { ID, Step } from "@/lib/api/types";

export interface TraceNode {
  step: Step;
  /** Depth in the tree built here. Equals `step.depth` whenever the parent chain is intact. */
  depth: number;
  children: TraceNode[];
  /** Every step below this one, at any depth. */
  descendantCount: number;
  /** For a step that was tried more than once: how many attempts its name has under the same parent. */
  attempts: number;
}

export interface TraceRow {
  node: TraceNode;
  step: Step;
  depth: number;
  hasChildren: boolean;
  collapsed: boolean;
}

export interface TraceTree {
  roots: TraceNode[];
  byId: Map<ID, TraceNode>;
  /** Parent id of each step that has a parent present in this trace. */
  parentOf: Map<ID, ID>;
}

/**
 * Build the tree from `parent_step_id`. A step whose parent is not in the trace, or whose parent
 * chain loops, becomes a root, which is how the backend lays such steps out too.
 */
export function buildTree(steps: Step[]): TraceTree {
  const sorted = [...steps].sort((a, b) => a.ordinal - b.ordinal);
  const byId = new Map<ID, TraceNode>(
    sorted.map((step) => [step.id, { step, depth: 0, children: [], descendantCount: 0, attempts: 1 }]),
  );
  const parentOf = new Map<ID, ID>();

  const loops = (step: Step): boolean => {
    const seen = new Set<ID>([step.id]);
    let parent = step.parent_step_id;
    while (parent !== null && byId.has(parent)) {
      if (seen.has(parent)) return true;
      seen.add(parent);
      parent = byId.get(parent)!.step.parent_step_id;
    }
    return false;
  };

  const roots: TraceNode[] = [];
  for (const step of sorted) {
    const node = byId.get(step.id)!;
    const parent = step.parent_step_id !== null && !loops(step) ? byId.get(step.parent_step_id) : undefined;
    if (parent) {
      parent.children.push(node);
      parentOf.set(step.id, parent.step.id);
    } else {
      roots.push(node);
    }
  }

  const finish = (nodes: TraceNode[], depth: number): number => {
    const attemptsByName = new Map<string, number>();
    for (const node of nodes) attemptsByName.set(node.step.name, (attemptsByName.get(node.step.name) ?? 0) + 1);
    let total = 0;
    for (const node of nodes) {
      node.depth = depth;
      node.attempts = attemptsByName.get(node.step.name)!;
      node.descendantCount = finish(node.children, depth + 1);
      total += 1 + node.descendantCount;
    }
    return total;
  };
  finish(roots, 0);
  return { roots, byId, parentOf };
}

/** The rows to draw, depth first, leaving out everything under a collapsed step. */
export function visibleRows(tree: TraceTree, collapsed: ReadonlySet<ID>): TraceRow[] {
  const rows: TraceRow[] = [];
  const walk = (nodes: TraceNode[]) => {
    for (const node of nodes) {
      const isCollapsed = collapsed.has(node.step.id);
      rows.push({ node, step: node.step, depth: node.depth, hasChildren: node.children.length > 0, collapsed: isCollapsed });
      if (!isCollapsed) walk(node.children);
    }
  };
  walk(tree.roots);
  return rows;
}

/** Ids of the steps above `stepId`, nearest first. */
export function ancestorsOf(tree: TraceTree, stepId: ID): ID[] {
  const ancestors: ID[] = [];
  let parent = tree.parentOf.get(stepId);
  while (parent !== undefined) {
    ancestors.push(parent);
    parent = tree.parentOf.get(parent);
  }
  return ancestors;
}

/** `collapsed` with every ancestor of `stepId` opened, so that step's row is visible. */
export function reveal(tree: TraceTree, collapsed: ReadonlySet<ID>, stepId: ID): ReadonlySet<ID> {
  const ancestors = ancestorsOf(tree, stepId).filter((id) => collapsed.has(id));
  if (ancestors.length === 0) return collapsed;
  const next = new Set(collapsed);
  for (const id of ancestors) next.delete(id);
  return next;
}
