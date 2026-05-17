import { useState, useCallback, useEffect } from 'react';

export interface MemeData {
  title: string;
  url: string;
  postLink: string;
  subreddit: string;
  ups: number;
}

interface UseMemeResult {
  meme: MemeData | null;
  loading: boolean;
  error: boolean;
  refresh: () => void;
}

const IMAGE_EXTS = ['.jpg', '.jpeg', '.png', '.gif', '.webp'];

function isImageUrl(url: string): boolean {
  const lower = url.toLowerCase();
  return IMAGE_EXTS.some((ext) => lower.includes(ext));
}

export function useMeme(subreddits: string | string[]): UseMemeResult {
  const [meme, setMeme] = useState<MemeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Stable string key avoids infinite re-render when caller passes an array literal
  const poolKey = Array.isArray(subreddits) ? subreddits.join(',') : subreddits;

  const fetchMeme = useCallback(async () => {
    setLoading(true);
    setError(false);
    const pool = poolKey.split(',');
    // Retry up to 5 times to get a non-nsfw image (skip videos/nsfw)
    for (let attempt = 0; attempt < 5; attempt++) {
      try {
        const pick = pool[Math.floor(Math.random() * pool.length)];
        const res = await fetch(`https://meme-api.com/gimme/${pick}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (data.nsfw || !isImageUrl(data.url)) continue;
        setMeme({
          title: data.title,
          url: data.url,
          postLink: data.postLink,
          subreddit: data.subreddit,
          ups: data.ups,
        });
        setLoading(false);
        return;
      } catch {
        // continue retrying
      }
    }
    setError(true);
    setLoading(false);
  }, [poolKey]);

  useEffect(() => {
    fetchMeme();
  }, [fetchMeme]);

  return { meme, loading, error, refresh: fetchMeme };
}
