import type { Node, Edge } from '@xyflow/react';
import { MarkerType } from '@xyflow/react';

export interface LayoutOptions {
  nodeWidth?: number;
  nodeHeight?: number;
  horizontalGap?: number;
  verticalGap?: number;
  topPadding?: number;
  leftPadding?: number;
}

export interface LayoutResult {
  nodes: Node[];
  edges: Edge[];
  hasCycle: boolean;
  cyclicEdges: Array<{ source: string; target: string }>;
}

export const getEdgeStyle = (relType: string) => {
  switch (relType) {
    case 'database_connection':
      return {
        stroke: '#f59e0b', // Amber
        strokeWidth: 2.5,
        strokeDasharray: '6,4',
        color: '#f59e0b',
        labelBg: '#78350f',
        animated: true,
      };
    case 'routes_traffic_to':
    case 'routes_to':
      return {
        stroke: '#06b6d4', // Cyan
        strokeWidth: 2.5,
        strokeDasharray: undefined,
        color: '#06b6d4',
        labelBg: '#164e63',
        animated: true,
      };
    case 'storage_access':
    case 'stores_in':
      return {
        stroke: '#a855f7', // Purple
        strokeWidth: 2,
        strokeDasharray: undefined,
        color: '#a855f7',
        labelBg: '#581c87',
        animated: false,
      };
    case 'protected_by_security_group':
      return {
        stroke: '#10b981', // Emerald
        strokeWidth: 1.5,
        strokeDasharray: '3,3',
        color: '#10b981',
        labelBg: '#064e3b',
        animated: false,
      };
    case 'enclosed_in_subnet':
    case 'member_of_vpc':
    case 'hosted_on':
      return {
        stroke: '#64748b', // Slate
        strokeWidth: 1.5,
        strokeDasharray: undefined,
        color: '#64748b',
        labelBg: '#1e293b',
        animated: false,
      };
    case 'authorizes_traffic_from':
      return {
        stroke: '#ec4899', // Pink
        strokeWidth: 1.5,
        strokeDasharray: '4,4',
        color: '#ec4899',
        labelBg: '#831843',
        animated: false,
      };
    default:
      return {
        stroke: '#94a3b8',
        strokeWidth: 1.5,
        strokeDasharray: undefined,
        color: '#94a3b8',
        labelBg: '#1e293b',
        animated: false,
      };
  }
};

/**
 * Calculates a deterministic, stable hierarchical layout for IT infrastructure digital twin graphs.
 * Guarantees:
 * 1. Directional consistency: if A -> B, A always visually appears above B.
 * 2. Dynamic ranking: ranks are computed from graph dependencies, not hardcoded resource types.
 * 3. Position stability: existing nodes retain horizontal and vertical positions whenever valid.
 * 4. Multiple roots: independent subtrees are laid out side-by-side without overlap.
 * 5. Disconnected nodes: isolated resources remain visible.
 * 6. Cycle handling: cycle back-edges are detected, preventing infinite loops while preserving edges.
 */
export function calculateTopologyLayout(
  components: any[],
  dependencies: any[],
  existingNodes?: Node[],
  options: LayoutOptions = {}
): LayoutResult {
  const {
    nodeWidth = 220,
    nodeHeight = 85,
    horizontalGap = 60,
    verticalGap = 85,
    topPadding = 60,
    leftPadding = 60
  } = options;

  if (!components || components.length === 0) {
    return { nodes: [], edges: [], hasCycle: false, cyclicEdges: [] };
  }

  // Map of existing node positions for stability
  const existingPosMap = new Map<string, { x: number; y: number }>();
  if (existingNodes) {
    for (const node of existingNodes) {
      if (node.position && typeof node.position.x === 'number' && typeof node.position.y === 'number') {
        existingPosMap.set(node.id, { x: node.position.x, y: node.position.y });
      }
    }
  }

  const compMap = new Map<string, any>();
  for (const c of components) {
    compMap.set(c.id, c);
  }

  // 1. Build Adjacency Structures
  const validEdges: Array<{ id: string; source: string; target: string; data: any }> = [];
  const outgoing = new Map<string, string[]>();
  const incoming = new Map<string, string[]>();
  const undirected = new Map<string, Set<string>>();

  for (const c of components) {
    outgoing.set(c.id, []);
    incoming.set(c.id, []);
    undirected.set(c.id, new Set<string>());
  }

  const seenEdges = new Set<string>();
  (dependencies || []).forEach((d: any, idx: number) => {
    const src = d.source_component_id || d.source_id;
    const tgt = d.target_component_id || d.target_id;

    if (src && tgt && compMap.has(src) && compMap.has(tgt) && src !== tgt) {
      const edgeKey = `${src}->${tgt}`;
      if (!seenEdges.has(edgeKey)) {
        seenEdges.add(edgeKey);
        const edgeId = d.id || `e-${idx}-${src}-${tgt}`;
        validEdges.push({ id: edgeId, source: src, target: tgt, data: d });

        outgoing.get(src)!.push(tgt);
        incoming.get(tgt)!.push(src);
        undirected.get(src)!.add(tgt);
        undirected.get(tgt)!.add(src);
      }
    }
  });

  // 2. Partition into Weakly Connected Components (Forests)
  const visited = new Set<string>();
  const connectedComponents: string[][] = [];

  for (const c of components) {
    if (!visited.has(c.id)) {
      const componentNodes: string[] = [];
      const queue: string[] = [c.id];
      visited.add(c.id);

      while (queue.length > 0) {
        const curr = queue.shift()!;
        componentNodes.push(curr);

        const neighbors = undirected.get(curr) || new Set();
        for (const neighbor of neighbors) {
          if (!visited.has(neighbor)) {
            visited.add(neighbor);
            queue.push(neighbor);
          }
        }
      }

      connectedComponents.push(componentNodes);
    }
  }

  // Sort connected components so that components with existing nodes stay in consistent order
  connectedComponents.sort((compA, compB) => {
    let minXA = Infinity;
    let minXB = Infinity;

    for (const id of compA) {
      const pos = existingPosMap.get(id);
      if (pos && pos.x < minXA) minXA = pos.x;
    }
    for (const id of compB) {
      const pos = existingPosMap.get(id);
      if (pos && pos.y < minXB) minXB = pos.x;
    }

    if (minXA !== Infinity && minXB !== Infinity) return minXA - minXB;
    if (minXA !== Infinity) return -1;
    if (minXB !== Infinity) return 1;
    return compB.length - compA.length;
  });

  // 3. Process Each Connected Component
  const calculatedPositions = new Map<string, { x: number; y: number }>();
  let currentComponentOffsetX = leftPadding;
  let overallHasCycle = false;
  const cyclicEdges: Array<{ source: string; target: string }> = [];

  for (const compNodes of connectedComponents) {
    const compNodeSet = new Set(compNodes);

    // Filter edges belonging strictly to this connected component
    const compEdges = validEdges.filter(
      (e) => compNodeSet.has(e.source) && compNodeSet.has(e.target)
    );

    // 3a. Cycle Detection using DFS 3-Coloring (0: WHITE, 1: GRAY, 2: BLACK)
    const color = new Map<string, number>();
    for (const id of compNodes) color.set(id, 0);

    const backEdgeSet = new Set<string>();

    const dfsCycle = (u: string) => {
      color.set(u, 1); // GRAY (visiting)
      const children = outgoing.get(u) || [];

      for (const v of children) {
        if (!compNodeSet.has(v)) continue;
        const vColor = color.get(v) || 0;

        if (vColor === 1) {
          // Found back-edge!
          overallHasCycle = true;
          backEdgeSet.add(`${u}->${v}`);
          cyclicEdges.push({ source: u, target: v });
        } else if (vColor === 0) {
          dfsCycle(v);
        }
      }

      color.set(u, 2); // BLACK (visited)
    };

    for (const id of compNodes) {
      if ((color.get(id) || 0) === 0) {
        dfsCycle(id);
      }
    }

    // 3b. Build DAG edges excluding back-edges for ranking
    const dagOutgoing = new Map<string, string[]>();
    const dagIncoming = new Map<string, string[]>();
    for (const id of compNodes) {
      dagOutgoing.set(id, []);
      dagIncoming.set(id, []);
    }

    for (const e of compEdges) {
      if (!backEdgeSet.has(`${e.source}->${e.target}`)) {
        dagOutgoing.get(e.source)!.push(e.target);
        dagIncoming.get(e.target)!.push(e.source);
      }
    }

    // 3c. Compute Topological Ranks (Longest Path in DAG)
    // Sources (roots): nodes with 0 incoming DAG edges in this component
    const ranks = new Map<string, number>();
    const inDegree = new Map<string, number>();

    for (const id of compNodes) {
      const incCount = dagIncoming.get(id)!.length;
      inDegree.set(id, incCount);
      ranks.set(id, 0);
    }

    // Roots queue
    const queue: string[] = [];
    for (const id of compNodes) {
      if (inDegree.get(id) === 0) {
        queue.push(id);
      }
    }

    // If pure cycle with no 0 in-degree, pick node with lowest in-degree / highest out-degree as root
    if (queue.length === 0 && compNodes.length > 0) {
      let bestRoot = compNodes[0];
      let maxOut = -1;
      for (const id of compNodes) {
        const outCnt = dagOutgoing.get(id)!.length;
        if (outCnt > maxOut) {
          maxOut = outCnt;
          bestRoot = id;
        }
      }
      queue.push(bestRoot);
      inDegree.set(bestRoot, 0);
    }

    // Topological traversal
    while (queue.length > 0) {
      const curr = queue.shift()!;
      const currRank = ranks.get(curr)!;
      const targets = dagOutgoing.get(curr) || [];

      for (const target of targets) {
        const newTargetRank = Math.max(ranks.get(target) || 0, currRank + 1);
        ranks.set(target, newTargetRank);

        const remainingInDegree = (inDegree.get(target) || 1) - 1;
        inDegree.set(target, remainingInDegree);

        if (remainingInDegree === 0) {
          queue.push(target);
        }
      }
    }

    // Fallback: any node not visited in DAG traversal gets rank assigned based on parents
    for (const id of compNodes) {
      if (!ranks.has(id)) ranks.set(id, 0);
    }

    // 3d. Group Nodes by Layer/Rank
    const layers = new Map<number, string[]>();
    let maxRank = 0;

    for (const id of compNodes) {
      const r = ranks.get(id) || 0;
      if (r > maxRank) maxRank = r;
      if (!layers.has(r)) layers.set(r, []);
      layers.get(r)!.push(id);
    }

    // 3e. Determine Horizontal Order within each Layer with Stability
    const slotWidth = nodeWidth + horizontalGap;

    for (let r = 0; r <= maxRank; r++) {
      const layerNodes = layers.get(r) || [];
      if (layerNodes.length === 0) continue;

      // Sort nodes within the layer to maintain stability:
      // Priority 1: If existing node had an X position, preserve relative order
      // Priority 2: If new node has parents, order near average X of parents
      // Priority 3: Fallback to name/id
      layerNodes.sort((a, b) => {
        const posA = existingPosMap.get(a);
        const posB = existingPosMap.get(b);

        if (posA && posB) return posA.x - posB.x;
        if (posA && !posB) return -1;
        if (!posA && posB) return 1;

        // Both are new: check average parent X
        const parentsA = dagIncoming.get(a) || [];
        const parentsB = dagIncoming.get(b) || [];
        const avgParentXA = parentsA.length > 0
          ? parentsA.reduce((sum, p) => sum + (existingPosMap.get(p)?.x || 0), 0) / parentsA.length
          : 0;
        const avgParentXB = parentsB.length > 0
          ? parentsB.reduce((sum, p) => sum + (existingPosMap.get(p)?.x || 0), 0) / parentsB.length
          : 0;

        if (avgParentXA !== avgParentXB) return avgParentXA - avgParentXB;
        return a.localeCompare(b);
      });
    }

    // 3f. Compute Coordinates for this Component
    // Find maximum layer width to center narrower layers
    let maxNodesInLayer = 0;
    for (let r = 0; r <= maxRank; r++) {
      const count = (layers.get(r) || []).length;
      if (count > maxNodesInLayer) maxNodesInLayer = count;
    }

    const componentWidth = Math.max(1, maxNodesInLayer) * slotWidth - horizontalGap;

    for (let r = 0; r <= maxRank; r++) {
      const layerNodes = layers.get(r) || [];
      const layerCount = layerNodes.length;
      const layerWidth = layerCount * slotWidth - horizontalGap;
      // Center layer horizontally relative to the component width
      const layerStartOffset = currentComponentOffsetX + Math.max(0, (componentWidth - layerWidth) / 2);

      layerNodes.forEach((nodeId, colIndex) => {
        const y = topPadding + r * (nodeHeight + verticalGap);
        const targetX = layerStartOffset + colIndex * slotWidth;

        // Stability Check: if node previously existed, keep its X close if within bounds
        const prev = existingPosMap.get(nodeId);
        let finalX = targetX;

        // If it's the only node in the layer and has an existing X within this component's horizontal span, preserve it
        if (prev && layerCount === 1 && prev.x >= currentComponentOffsetX && prev.x <= currentComponentOffsetX + componentWidth) {
          finalX = prev.x;
        }

        calculatedPositions.set(nodeId, { x: Math.round(finalX), y: Math.round(y) });
      });
    }

    // Advance offset for the next independent connected component
    currentComponentOffsetX += componentWidth + horizontalGap * 1.5;
  }

  // 4. Generate React Flow Nodes
  const nodes: Node[] = components.map((c: any) => {
    const pos = calculatedPositions.get(c.id) || { x: leftPadding, y: topPadding };
    const prevNode = (existingNodes || []).find((n) => n.id === c.id);

    return {
      id: c.id,
      type: 'custom',
      position: pos,
      data: {
        ...c,
        blastRadius: prevNode?.data?.blastRadius || false
      },
      selected: prevNode?.selected || false
    };
  });

  // 5. Generate React Flow Edges with Hierarchical Direction
  const edges: Edge[] = validEdges.map((e) => {
    const relType = e.data?.relationship_type || 'connects_to';
    const edgeConfig = getEdgeStyle(relType);
    const formattedLabel = relType.replace(/_/g, ' ');

    return {
      id: e.id,
      source: e.source,
      target: e.target,
      type: 'smoothstep',
      animated: edgeConfig.animated,
      label: formattedLabel,
      style: {
        stroke: edgeConfig.stroke,
        strokeWidth: edgeConfig.strokeWidth,
        strokeDasharray: edgeConfig.strokeDasharray
      },
      labelStyle: { fill: '#e2e8f0', fontSize: 10, fontWeight: 600 },
      labelBgStyle: { fill: edgeConfig.labelBg, fillOpacity: 0.9, rx: 4, ry: 4 },
      labelBgPadding: [6, 4] as [number, number],
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: edgeConfig.color
      },
      data: e.data
    };
  });

  return {
    nodes,
    edges,
    hasCycle: overallHasCycle,
    cyclicEdges
  };
}
