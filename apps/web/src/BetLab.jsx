import React from 'react';
import SGPLab from './sgp/SGPLab';

export default function BetLab({ authToken }) {
  return <SGPLab embedded authToken={authToken} />;
}
