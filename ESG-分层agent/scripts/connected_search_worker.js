// Execute through functions.exec, not Node: tools is the connected tool runtime.
const root='/Users/liusuyao/code/python_code/IS/ESG-agent/ESG-分层agent';
const quote=s=>"'"+s.replace(/'/g,"'\\''")+"'";
let answered=0;const started=Date.now();
while(Date.now()-started<21600000){
 const p=await tools.exec_command({cmd:'python3 '+quote(root+'/scripts/pending_search_requests.py'),max_output_tokens:8000});
 if(p.exit_code!==0)throw new Error('Search queue unavailable');
 for(const req of JSON.parse(p.output)){
  let result;let succeeded=false;
  for(let attempt=0;attempt<3;attempt++){
   try{
    result=await tools.web__run({search_query:[{q:req.query,...(req.domains?.length?{domains:req.domains}:{})}],response_length:'long'});
    const raw=typeof result==='string'?result:JSON.stringify(result);
    if(result?.isError||/^Internal Error/.test(raw))throw new Error('Search provider error');
    const urls=[...new Set((raw.match(/https?:\/\/[^\s)>\]"\\]+/g)||[]).map(u=>u.replace(/[.,;]+$/,'')))];
    const lines=raw.split('\n');const results=urls.map(url=>({url,title:(lines.find(l=>l.includes(url)&&l.includes(' ('))||'').split(' (')[0]||url}));
    const record={request_id:req.request_id,query:req.query,backend:'connected_web_search',search_executed:true,results,raw_search_response:raw,actual_source_opening_complete:false,actual_search_time_utc:new Date().toISOString()};
    const relative=req.response_path.replace('/Users/liusuyao/code/python_code/IS/ESG-agent/','');
    await tools.apply_patch('*** Begin Patch\n*** Add File: '+relative+'\n+'+JSON.stringify(record,null,2).split('\n').join('\n+')+'\n*** End Patch');
    const check=await tools.exec_command({cmd:'python3 -c '+quote('from pathlib import Path; assert Path('+JSON.stringify(req.response_path)+').is_file()'),max_output_tokens:100});
    if(check.exit_code!==0)throw new Error('Search response was not saved');
    succeeded=true;answered++;break;
   }catch(error){if(attempt<2)await new Promise(resolve=>setTimeout(resolve,10000));}
  }
  if(!succeeded)text({request:req.request_id,state:'search_failed_after_retries'});
 }
 const status=await tools.exec_command({cmd:'python3 -c '+quote('import json; from pathlib import Path; print(json.loads(Path('+JSON.stringify(root+'/runs/full5_20261127/supervisor_status.json')+').read_text()).get("state",""))'),max_output_tokens:100});
 if(['completed','failed_after_bounded_retries'].includes(status.output.trim())){text({answered,supervisor:status.output.trim()});exit();}
 await new Promise(resolve=>setTimeout(resolve,30000));
}
text({answered,state:'search_worker_time_limit'});
