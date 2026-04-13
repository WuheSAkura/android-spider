import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

const STORAGE_PREFIX = "android-spider.desktop.v1";

function buildStorageKey(key: string): string {
  return `${STORAGE_PREFIX}:${key}`;
}

function readPersistentValue<T>(storageKey: string, initialValue: T): T {
  if (typeof window === "undefined") {
    return initialValue;
  }

  try {
    const rawValue = window.localStorage.getItem(storageKey);
    if (rawValue === null) {
      return initialValue;
    }
    return JSON.parse(rawValue) as T;
  } catch {
    return initialValue;
  }
}

export function usePersistentState<T>(key: string, initialValue: T): [T, Dispatch<SetStateAction<T>>] {
  const storageKey = buildStorageKey(key);
  const [state, setState] = useState<T>(() => readPersistentValue(storageKey, initialValue));

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(state));
    } catch {
      // Ignore storage write failures and keep the in-memory state usable.
    }
  }, [state, storageKey]);

  return [state, setState];
}
