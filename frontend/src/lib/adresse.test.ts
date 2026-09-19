import { describe, expect, it } from 'vitest';

import { sichereAdresse } from '@/lib/adresse';

describe('sichereAdresse', () => {
  it('laesst nur https durch', () => {
    expect(sichereAdresse('https://www.reuters.com/x?y=1')).toBe('https://www.reuters.com/x?y=1');
    expect(sichereAdresse('http://www.reuters.com/x')).toBeNull();
    expect(sichereAdresse('javascript:alert(1)')).toBeNull();
    expect(sichereAdresse('data:text/html,hi')).toBeNull();
    expect(sichereAdresse('HTTPS://EXAMPLE.COM')).toBe('https://example.com/');
  });

  it('macht aus Unsinn keinen Link', () => {
    expect(sichereAdresse('kein link')).toBeNull();
    expect(sichereAdresse(null)).toBeNull();
    expect(sichereAdresse(undefined)).toBeNull();
    expect(sichereAdresse('')).toBeNull();
  });
});
