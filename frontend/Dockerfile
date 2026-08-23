# Runs the Vite dev server rather than a production nginx build — a deliberate
# simplification for this take-home's "one-command startup" requirement (see
# README "Scope simplifications"). For a real deployment, swap this for a
# multi-stage build that runs `npm run build` and serves the static output.
FROM node:20-slim

WORKDIR /app

COPY frontend/package.json ./package.json
RUN npm install

COPY frontend/ ./

EXPOSE 5173

CMD ["npm", "run", "dev"]
