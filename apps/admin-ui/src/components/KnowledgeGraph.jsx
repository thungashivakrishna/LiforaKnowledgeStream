import React, { useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

const KnowledgeGraph = ({ facts, tags, width, height }) => {
  const graphData = useMemo(() => {
    const nodes = [];
    const links = [];
    const nodeIds = new Set();

    // 1. Process Tags as central hubs (Frameworks/Topics)
    tags.forEach(tag => {
      if (!nodeIds.has(tag.tag_value)) {
        nodes.push({
          id: tag.tag_value,
          name: tag.tag_value,
          type: tag.tag_type,
          color: tag.tag_type === 'FRAMEWORK' ? '#f59e0b' : '#3b82f6',
          val: tag.tag_type === 'FRAMEWORK' ? 5 : 3
        });
        nodeIds.add(tag.tag_value);
      }
    });

    // 2. Process Facts as Entities and Relationships
    facts.forEach(fact => {
      if (fact.subject && fact.predicate && fact.object) {
        if (!nodeIds.has(fact.subject)) {
          nodes.push({ id: fact.subject, name: fact.subject, type: 'ENTITY', color: '#10b981', val: 4 });
          nodeIds.add(fact.subject);
        }
        if (!nodeIds.has(fact.object)) {
          nodes.push({ id: fact.object, name: fact.object, type: 'ENTITY', color: '#6366f1', val: 3 });
          nodeIds.add(fact.object);
        }
        
        links.push({
          source: fact.subject,
          target: fact.object,
          label: fact.predicate,
          color: '#475569'
        });
      }
    });

    return { nodes, links };
  }, [facts, tags]);

  return (
    <div className="bg-slate-950 rounded-2xl border border-slate-800 overflow-hidden shadow-inner">
      <ForceGraph2D
        graphData={graphData}
        width={width || 600}
        height={height || 400}
        nodeLabel="name"
        nodeColor={node => node.color}
        nodeVal={node => node.val}
        linkLabel="label"
        linkDirectionalArrowLength={3.5}
        linkDirectionalArrowRelPos={1}
        linkCurvature={0.25}
        linkColor={() => '#334155'}
        nodeCanvasObject={(node, ctx, globalScale) => {
          const label = node.name;
          const fontSize = 12/globalScale;
          ctx.font = `${fontSize}px Inter, sans-serif`;
          const textWidth = ctx.measureText(label).width;
          const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.2); 

          ctx.fillStyle = 'rgba(15, 23, 42, 0.8)';
          ctx.fillRect(node.x - bckgDimensions[0] / 2, node.y - bckgDimensions[1] / 2, ...bckgDimensions);

          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillStyle = node.color;
          ctx.fillText(label, node.x, node.y);

          node.__bckgDimensions = bckgDimensions; // to use in nodePointerAreaPaint
        }}
      />
    </div>
  );
};

export default KnowledgeGraph;
