import React from 'react';
import { Link } from 'react-router-dom';
import Icon from '../icons';
import { Card, Empty } from '../components/ui';

export default function NotFound() {
  return (
    <Card><Empty
      icon={Icon.Search}
      title="No such page"
      body="That route does not exist. Press ⌘K to search for a player, team or coach."
      action={<Link className="btn btn-primary btn-sm" to="/slate">Back to the slate</Link>}
    /></Card>
  );
}
