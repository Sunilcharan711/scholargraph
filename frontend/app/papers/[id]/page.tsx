import Reader from "./reader";
export default async function Page({params}:{params:Promise<{id:string}>}) {
  const {id}=await params;
  return <Reader key={id} id={id}/>;
}
