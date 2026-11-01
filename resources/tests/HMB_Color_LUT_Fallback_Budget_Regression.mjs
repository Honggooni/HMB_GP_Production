import assert from 'node:assert/strict';
import {hmbColorLUTFallbackBudget,hmbColorLUTCube,hmbColorLUTGradePixels} from '../../widgets/HMBColorLUTLibraryWidget.js';

const budget=hmbColorLUTFallbackBudget();
assert.equal(budget.width,640);assert.equal(budget.fps,30);assert.equal(budget.due(0),true);
budget.mark(100);assert.equal(budget.due(110),false);assert.equal(budget.due(134),true);
for(let i=0;i<3;i++)budget.observe(18);
assert.equal(budget.width,480,'Sustained complete draw cost reduces preview resolution.');
for(let i=0;i<3;i++)budget.observe(18);
assert.equal(budget.width,320);
for(let i=0;i<4;i++)budget.observe(28);
assert.equal(budget.fps,12,'Overloaded minimum size also limits preview cadence.');
for(let i=0;i<59;i++)budget.observe(1);
assert.equal(budget.width,320,'Hysteresis avoids rapid resolution oscillation.');
for(let i=0;i<8;i++)budget.observe(1);
assert.equal(budget.width,480);
budget.reset();assert.equal(budget.width,640);assert.equal(budget.fps,30);assert.equal(budget.due(0),true);
for(const invalid of [NaN,Infinity,-1])budget.observe(invalid);
assert.equal(budget.width,640);
// Adaptive bookkeeping cannot change the existing fallback color computation.
const cube=hmbColorLUTCube({enabled:true,exposure:.5,saturation:.25});
const before=Uint8ClampedArray.from([14,76,138,255,207,121,32,255]);
const a=hmbColorLUTGradePixels(before.slice(),2,cube,2,.5);
for(let i=0;i<10;i++)budget.observe(30);
const b=hmbColorLUTGradePixels(before.slice(),2,cube,2,.5);
assert.deepEqual(a,b);
console.log('LUT fallback preview budget: cadence, hysteresis, source reset and unchanged pixel math PASS');
