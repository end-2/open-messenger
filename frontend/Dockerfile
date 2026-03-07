FROM node:22-alpine

WORKDIR /app

COPY frontend/package.json ./package.json
COPY frontend/src ./src

EXPOSE 3001

CMD ["npm", "run", "dev"]
