import { Position, type Node, type Edge } from '@xyflow/react';

const NODE_WIDTH = 220;
const NODE_HEIGHT = 110;

/**
 * Automatically computes clean hierarchical coordinates for React Flow nodes based on dependency ranks.
 */
export function getLayoutedElements(nodes: Node[], edges: Edge[], direction: 'TB' | 'LR' = 'TB'): { nodes: Node[]; edges: Edge[] } {
  const isHorizontal = direction === 'LR';
  
  // Calculate in-degree to determine rank levels
  const inDegree: Record<string, number> = {};
  const adj: Record<string, string[]> = {};
  
  nodes.forEach(n => {
    inDegree[n.id] = 0;
    adj[n.id] = [];
  });
  
  edges.forEach(e => {
    if (adj[e.source]) adj[e.source].push(e.target);
    if (inDegree[e.target] !== undefined) inDegree[e.target] += 1;
  });
  
  const levels: Record<string, number> = {};
  const queue = nodes.filter(n => (inDegree[n.id] || 0) === 0).map(n => n.id);
  queue.forEach(id => { levels[id] = 0; });
  
  let head = 0;
  while (head < queue.length) {
    const u = queue[head++];
    const curLevel = levels[u] || 0;
    (adj[u] || []).forEach(v => {
      levels[v] = Math.max(levels[v] || 0, curLevel + 1);
      inDegree[v] -= 1;
      if (inDegree[v] <= 0) {
        queue.push(v);
      }
    });
  }
  
  // Group nodes by level
  const rankBuckets: Record<number, Node[]> = {};
  nodes.forEach(n => {
    const rank = levels[n.id] || 0;
    if (!rankBuckets[rank]) rankBuckets[rank] = [];
    rankBuckets[rank].push(n);
  });
  
  const layoutedNodes: Node[] = [];
  Object.entries(rankBuckets).forEach(([rankStr, bucketNodes]) => {
    const rank = parseInt(rankStr, 10);
    bucketNodes.forEach((node, idx) => {
      const x = isHorizontal ? rank * (NODE_WIDTH + 100) + 60 : idx * (NODE_WIDTH + 60) + 60;
      const y = isHorizontal ? idx * (NODE_HEIGHT + 60) + 60 : rank * (NODE_HEIGHT + 80) + 60;
      
      layoutedNodes.push({
        ...node,
        targetPosition: isHorizontal ? Position.Left : Position.Top,
        sourcePosition: isHorizontal ? Position.Right : Position.Bottom,
        position: { x, y }
      });
    });
  });
  
  return { nodes: layoutedNodes, edges };
}
