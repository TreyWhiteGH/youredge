import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import AppShell from './components/AppShell';
import Slate from './pages/Slate';
import Live from './pages/Live';
import GameDetail from './pages/GameDetail';
import Teams from './pages/Teams';
import TeamDetail from './pages/TeamDetail';
import Players from './pages/Players';
import PlayerDetail from './pages/PlayerDetail';
import CoachDetail from './pages/CoachDetail';
import Compare from './pages/Compare';
import BetLab from './pages/BetLab';
import Coverage from './pages/Coverage';
import NotFound from './pages/NotFound';

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/slate" replace />} />
        <Route path="/slate" element={<Slate />} />
        <Route path="/live" element={<Live />} />
        {/* League sits in the path because a canonical id already carries it, and the
            engine 400s on a mismatch — keeping them together makes links self-checking. */}
        <Route path="/games/:league/:gameId" element={<GameDetail />} />
        <Route path="/teams" element={<Teams />} />
        <Route path="/teams/:league/:teamId" element={<TeamDetail />} />
        <Route path="/players" element={<Players />} />
        <Route path="/players/:playerId" element={<PlayerDetail />} />
        <Route path="/coaches/:coachId" element={<CoachDetail />} />
        <Route path="/compare" element={<Compare />} />
        <Route path="/lab" element={<BetLab />} />
        <Route path="/data" element={<Coverage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
