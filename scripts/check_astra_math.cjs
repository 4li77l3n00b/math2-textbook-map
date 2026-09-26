const fs=require('fs'),vm=require('vm'),path=require('path');
const root=path.resolve(__dirname,'..'),out=path.join(root,'output/astra');
const ctx={window:{}};vm.runInNewContext(fs.readFileSync(path.join(out,'assets/katex-offline.js'),'utf8'),ctx);
const errors=[];let formulas=0;
const macros={'\\R':'\\mathbb{R}','\\rank':'\\operatorname{rank}','\\arccot':'\\operatorname{arccot}','\\sgn':'\\operatorname{sgn}','\\d':'\\mathrm{d}'};
for(const file of fs.readdirSync(path.join(out,'final')).filter(x=>x.endsWith('.json'))){
  const doc=JSON.parse(fs.readFileSync(path.join(out,'final',file),'utf8'));
  for(const q of doc.questions){
    for(const [field,text] of Object.entries({stem:q.stem,answer:q.answer,solution:q.solution,review:q.review.explanation,repo_review:q.repo_review?.explanation??'',notes:q.notes.join('\n')})){
      for(const m of text.matchAll(/\$\$([\s\S]*?)\$\$|\\\[([\s\S]*?)\\\]|(?<!\\)\$([^$]+?)(?<!\\)\$|\\\(([\s\S]*?)\\\)/g)){
        formulas++;
        const expr=m[1]??m[2]??m[3]??m[4];
        try{ctx.window.katex.renderToString(expr,{displayMode:m[1]!==undefined||m[2]!==undefined,throwOnError:true,strict:'ignore',trust:false,macros});}
        catch(e){errors.push({id:q.question_id,field,expression:expr,error:String(e)});}
      }
    }
  }
}
fs.writeFileSync(path.join(out,'math-validation.json'),JSON.stringify({formulas,errors},null,2)+'\n');
console.log(JSON.stringify({formulas,errors:errors.length,examples:errors.slice(0,20)},null,2));
process.exitCode=errors.length?1:0;
