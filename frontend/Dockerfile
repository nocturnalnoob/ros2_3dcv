# Frontend dev image. For production, `npm run build` and serve dist/ via a CDN.
FROM node:20-slim
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
