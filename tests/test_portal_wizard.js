// Execute the real portal script against a minimal DOM to exercise reconnect handling.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('voiceservices/static/portal.js','utf8');
function context(overrides={}) {
 const intervals=[],storage=new Map();
 const document={documentElement:{classList:{add(){}}},querySelector(){return null;},addEventListener(){},getElementById(){return null;}};
 const sandbox={document,window:{addEventListener(){}},localStorage:{getItem(){return null;}},sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},location:{href:'http://localhost/admin/host',pathname:'/admin/host'},URL,setInterval:fn=>intervals.push(fn),clearTimeout(){},setTimeout(){},...overrides};
 return {sandbox,intervals,storage,document};
}
(async()=>{
 const setup=context(),message={textContent:'',classList:{toggle(){}}};let requests=0;
 const panel={dataset:{updateState:'running',updateVersion:'1.0.0'},isConnected:true,querySelector:()=>message,querySelectorAll:()=>[]};
 setup.document.querySelector=selector=>selector.startsWith('[data-update-state=') && panel.dataset.updateState==='running'?panel:null;
 setup.sandbox.fetch=async url=>{requests++;if(url==='/admin/update-status')return {ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>({version:'1.0.0',status:{kind:'insap',state:'complete',message:'Updated'}})};throw Error('Portal restarting');};
 vm.runInNewContext(source,setup.sandbox);
 await setup.intervals[0]();assert.equal(panel.dataset.updateState,'running');assert.match(message.textContent,/reconnecting/);
 await setup.intervals[0]();assert.equal(requests,4,'Completion reconnect must continue polling after a failed page load');
 const pending=context();let opened=0;
 pending.storage.set('insap-update-wizard','update-insap');
 pending.document.getElementById=id=>id==='update-insap'?{id,open:false,matches:()=>true,hasAttribute:()=>true,showModal(){opened++;}}:null;
 vm.runInNewContext(source,pending.sandbox);assert.equal(opened,1);assert.equal(pending.storage.has('insap-update-wizard'),false,'Finished workflows must not reopen on the next visit');
 console.log('2 wizard behavior checks passed');
})();
