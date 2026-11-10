import { defineCollection } from 'astro:content';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

// Required by Astro 6: without it the build fails with "The collection docs does not exist or is empty".
export const collections = { docs: defineCollection({ loader: docsLoader(), schema: docsSchema() }) };
