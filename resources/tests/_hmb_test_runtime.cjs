// Shared interpreter selection for CommonJS contract fixtures; never a user-specific path.
const fs=require('node:fs'),path=require('node:path');
function regressionPython(root,override){
 const local=path.join(root,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
 return override||process.env.HMB_REGRESSION_PYTHON||process.env.HMB_TEST_PYTHON
  ||process.env.HMB_NATIVE_HEADER_PYTHON||(fs.existsSync(local)?local:(process.platform==='win32'?'python':'python3'));
}
module.exports={regressionPython};
