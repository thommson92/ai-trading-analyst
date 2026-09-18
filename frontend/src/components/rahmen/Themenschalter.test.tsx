import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { Themenschalter } from '@/components/rahmen/Themenschalter';

beforeEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset['thema'];
});

afterEach(() => {
  cleanup();
});

describe('Der Themenschalter', () => {
  it('bietet beim Standard den Wechsel ins Helle an', () => {
    render(<Themenschalter />);

    expect(screen.getByRole('button', { name: 'Helles Design' })).toBeTruthy();
    expect(document.documentElement.dataset['thema']).toBeUndefined();
  });

  it('wechselt, merkt sich die Wahl und bietet den Rueckweg an', () => {
    render(<Themenschalter />);

    fireEvent.click(screen.getByRole('button', { name: 'Helles Design' }));

    expect(document.documentElement.dataset['thema']).toBe('hell');
    expect(window.localStorage.getItem('ata-thema')).toBe('hell');
    expect(screen.getByRole('button', { name: 'Dunkles Design' })).toBeTruthy();
  });

  it('wendet eine gemerkte Wahl beim Laden an', () => {
    window.localStorage.setItem('ata-thema', 'hell');

    render(<Themenschalter />);

    expect(document.documentElement.dataset['thema']).toBe('hell');
    expect(screen.getByRole('button', { name: 'Dunkles Design' })).toBeTruthy();
  });
});
