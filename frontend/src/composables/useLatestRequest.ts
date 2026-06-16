export function useLatestRequest() {
  let sequence = 0;

  function next(): number {
    sequence += 1;
    return sequence;
  }

  function isCurrent(requestId: number): boolean {
    return requestId === sequence;
  }

  function invalidate(): void {
    sequence += 1;
  }

  return {
    next,
    isCurrent,
    invalidate
  };
}
