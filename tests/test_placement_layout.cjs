const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=require('node:path').join(__dirname,'..');
const app=fs.readFileSync(root+'/web/app.js','utf8');
const ctx=vm.createContext({window:{}});
vm.runInContext(app.slice(app.indexOf('const isYearLongPlacement'),app.indexOf('function placementDivider'))+'\nthis.split=splitPlacementRows;',ctx);
vm.runInContext(fs.readFileSync(root+'/dist/gallery-data.js','utf8'),ctx);
const group={additional:true,choices:[{code:'CE2020'},{code:'CE2021'},{code:'CE2022'}]};
const split=ctx.split([group]);
assert.equal(JSON.stringify(split.rows[0].choices.map(x=>x.code)),'["CE2020","CE2022"]');
assert.equal(split.placements[0].choices[0].code,'CE2021');
assert.equal(group.choices.length,3);
assert.equal(ctx.split([{...group,additional:false}]).placements.length,0);
assert.equal(ctx.split([{...group,sourceConflict:true}]).placements.length,0);
assert.equal(ctx.split([{additional:true,code:'CE2021'}]).rows.length,0);
let count=0;
for(const c of ctx.window.COURSE_GALLERY.courses.filter(c=>c.level!=='PG')){
 const before=JSON.stringify(c.modules),r=ctx.split(c.modules);
 const total=xs=>xs.filter(x=>!x.additional&&!x.excludedFromAward).reduce((a,x)=>a+(x.credits||0),0);
 assert.equal(total(r.rows),total(c.modules));assert.equal(JSON.stringify(c.modules),before);
 for(const p of r.placements){assert(c.modules.some(x=>x.stage>p.stage));count++;}
}
console.log('PASS: '+count+' placement entries; other choices, award totals and original data preserved.');
