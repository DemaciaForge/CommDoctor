import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
// import App from './App.tsx'  // 阶段01原型
import FaultDiagnosisApp from './FaultDiagnosisApp.tsx'  // 阶段02故障诊断

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <FaultDiagnosisApp />
  </StrictMode>,
)
