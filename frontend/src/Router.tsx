import { useEffect, useState } from 'react';
import App from './App';
import FaultDiagnosisApp from './FaultDiagnosisApp';
import DiagnosticChallengeApp from './DiagnosticChallengeApp';
import FrequencyOffsetApp from './FrequencyOffsetApp';
import MultiFaultApp from './MultiFaultApp';

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
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  // 导航栏
  const nav = (
    <nav style={{
      background: '#0A0D12',
      borderBottom: '1px solid #1E2636',
      padding: '0.75rem 1.5rem',
      display: 'flex',
      gap: '1rem',
      alignItems: 'center'
    }}>
      <span style={{ color: '#6EE7B7', fontWeight: 600 }}>CommDoctor</span>
      <a
        href="#/"
        style={{
          color: route === '/' ? '#38BDF8' : '#9CA3AF',
          textDecoration: 'none',
          padding: '0.5rem 1rem',
          borderRadius: '6px',
          background: route === '/' ? '#161D2B' : 'transparent'
        }}
      >
        Stage01 仿真
      </a>
      <a
        href="#/stage02"
        style={{
          color: route === '/stage02' ? '#38BDF8' : '#9CA3AF',
          textDecoration: 'none',
          padding: '0.5rem 1rem',
          borderRadius: '6px',
          background: route === '/stage02' ? '#161D2B' : 'transparent'
        }}
      >
        Stage02 故障诊断
      </a>
      <a
        href="#/stage03"
        style={{
          color: route === '/stage03' ? '#38BDF8' : '#9CA3AF',
          textDecoration: 'none',
          padding: '0.5rem 1rem',
          borderRadius: '6px',
          background: route === '/stage03' ? '#161D2B' : 'transparent'
        }}
      >
        Stage03 诊断挑战
      </a>
      <a
        href="#/stage04"
        style={{
          color: route === '/stage04' ? '#38BDF8' : '#9CA3AF',
          textDecoration: 'none',
          padding: '0.5rem 1rem',
          borderRadius: '6px',
          background: route === '/stage04' ? '#161D2B' : 'transparent'
        }}
      >
        Stage04 频偏诊断
      </a>
      <a
        href="#/stage05"
        style={{
          color: route === '/stage05' ? '#C084FC' : '#9CA3AF',
          textDecoration: 'none', padding: '0.5rem 1rem', borderRadius: '6px',
          background: route === '/stage05' ? '#211B2C' : 'transparent'
        }}
      >
        Stage05 联合诊断
      </a>
    </nav>
  );

  return (
    <>
      {nav}
      {route === '/' && <App />}
      {route === '/stage02' && <FaultDiagnosisApp />}
      {route === '/stage03' && <DiagnosticChallengeApp />}
      {route === '/stage04' && <FrequencyOffsetApp />}
      {route === '/stage05' && <MultiFaultApp />}
    </>
  );
}
