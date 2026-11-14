"use client";
import {useEffect,useRef} from "react";
import cytoscape from "cytoscape";

type Node={id:string;title:string};
export default function Network({paper,neighbors,onFocus}:{paper:Node;neighbors:{paper:Node;score:number}[];onFocus:(id:string)=>void}) {
 const container=useRef<HTMLDivElement>(null);
 const handler=useRef(onFocus);
 useEffect(()=>{handler.current=onFocus},[onFocus]);
 useEffect(()=>{
   if(!container.current)return;
   const cy=cytoscape({container:container.current, elements:[
     {data:{id:paper.id,label:"Focus"},classes:"focus",position:{x:0,y:0}},
     ...neighbors.flatMap(({paper:n},i)=>{
       const a=2*Math.PI*i/neighbors.length-Math.PI/2;
       return [{data:{id:n.id,label:String(i+1)},position:{x:120*Math.cos(a),y:95*Math.sin(a)}},
               {data:{id:"edge-"+n.id,source:paper.id,target:n.id}}];
     })],layout:{name:"preset",padding:32},minZoom:.4,maxZoom:2.5,
     style:[
       {selector:"node",style:{"background-color":"#94cbb2",label:"data(label)",color:"#10221a","text-valign":"center","font-size":12}},
       {selector:".focus",style:{width:48,height:48,"background-color":"#d2fce4"}},
       {selector:"edge",style:{width:2,"line-color":"#618977"}},
     ]});
   cy.on("tap","node",e=>{if(e.target.id()!==paper.id)handler.current(e.target.id())});
   const resize=new ResizeObserver(()=>{cy.resize();cy.fit(undefined,32)});
   resize.observe(container.current);
   return ()=>{resize.disconnect();cy.destroy()};
 },[paper,neighbors]);
 return <div ref={container} className="network" role="img" aria-label={`Related papers for ${paper.title}; select a paper below to explore it.`}/>;
}
