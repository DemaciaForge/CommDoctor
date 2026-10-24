import { useEffect, useState } from 'react';
import App from './App';
import FaultDiagnosisApp from './FaultDiagnosisApp';
import DiagnosticChallengeApp from './DiagnosticChallengeApp';
import FrequencyOffsetApp from './FrequencyOffsetApp';
import MultiFaultApp from './MultiFaultApp';
import PhaseOffsetApp from './PhaseOffsetApp';
import TripleFaultApp from './TripleFaultApp';
import TimingSynchronizationApp from './TimingSynchronizationApp';
import AppShell from './AppShell';

/**
 * 简单的 Hash 路由组件
 * / 或 #/ -> Stage01 BPSK 仿真
 * #/stage02 -> Stage02 故障诊断
 * #/stage03 -> Stage03 诊断挑战
 * #/stage04 -> Stage04 频率偏移实验室
 * #/stage05 -> Stage05 多故障联合诊断
 */
export default function Router() {
  const [route, setRoute] = useState(window.location.hash.slice(1) || '/');

  useEffect(() => {
    const handleHashChange = () => {
      setRoute(window.location.hash.slice(1) || '/');
      window.scrollTo({ top: 0, behavior: 'auto' });
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  return (
    <AppShell route={route}>
      {route === '/' && <App />}
      {route === '/stage02' && <FaultDiagnosisApp />}
      {route === '/stage03' && <DiagnosticChallengeApp />}
      {route === '/stage04' && <FrequencyOffsetApp />}
      {route === '/stage05' && <MultiFaultApp />}
      {route === '/stage06' && <PhaseOffsetApp />}
      {route === '/stage07' && <TripleFaultApp />}
      {route === '/stage08' && <TimingSynchronizationApp />}
    </AppShell>
  );
}
