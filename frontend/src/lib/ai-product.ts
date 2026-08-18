import type { AIVisibilityObservationItem } from "./api";

export type AIAppearance = "mentioned" | "cited_only" | "not_seen";
export type PromptRollup = {
  prompt: string; intentTopic: string; observations: AIVisibilityObservationItem[];
  mentionRate: number; citationRate: number | null; recommendationRate: null;
};

const percent = (part:number,total:number) => total ? Math.round(part / total * 100) : 0;

export function appearanceOf(item:AIVisibilityObservationItem):AIAppearance {
  if(item.mentioned)return "mentioned";
  if(item.citations.length || item.cited_domains.length)return "cited_only";
  return "not_seen";
}

export function groupPromptObservations(items:AIVisibilityObservationItem[]):PromptRollup[] {
  const groups=new Map<string,AIVisibilityObservationItem[]>();
  for(const item of items){const key=`${item.intent_topic}\u0000${item.prompt_text}`;groups.set(key,[...(groups.get(key)??[]),item]);}
  return [...groups.values()].map((observations)=>{
    const citationCapable=observations.filter((item)=>item.citations_available);
    return {prompt:observations[0]?.prompt_text??"",intentTopic:observations[0]?.intent_topic??"",observations,
      mentionRate:percent(observations.filter((item)=>item.mentioned).length,observations.length),
      citationRate:citationCapable.length?percent(citationCapable.filter((item)=>item.citations.length>0).length,citationCapable.length):null,
      recommendationRate:null};
  });
}

export function visibilityMetrics(items:AIVisibilityObservationItem[]) {
  const citationCapable=items.filter((item)=>item.citations_available);
  return {
    validAnswers:items.length,
    prompts:groupPromptObservations(items).length,
    surfaces:new Set(items.map((item)=>item.surface)).size,
    mentionRate:percent(items.filter((item)=>item.mentioned).length,items.length),
    recommendationRate:null as number|null,
    citationRate:citationCapable.length?percent(citationCapable.filter((item)=>item.citations.length>0).length,citationCapable.length):null,
    citationCapableAnswers:citationCapable.length,
  };
}

export function sourceDomains(items:AIVisibilityObservationItem[]){
  const counts=new Map<string,number>();
  for(const item of items)for(const domain of item.cited_domains)counts.set(domain,(counts.get(domain)??0)+1);
  return [...counts].map(([domain,count])=>({domain,count,share:percent(count,[...counts.values()].reduce((a,b)=>a+b,0))})).sort((a,b)=>b.count-a.count);
}

export function appearanceLabel(value:AIAppearance){return value==="mentioned"?"ذُكر دون تصنيف توصية":value==="cited_only"?"استُشهد به فقط":"لم يظهر"}
