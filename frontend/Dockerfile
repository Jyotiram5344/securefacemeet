# Stage 1: Build the React application
FROM node:18-alpine AS build

WORKDIR /app

# Copy package descriptors and install dependencies
COPY package*.json ./
RUN npm install

# Copy all source files
COPY . .

# Build the production assets (Vite will read VITE_API_BASE_URL from the .env file)
RUN npm run build

# Stage 2: Serve the application using a lightweight node server
FROM node:18-alpine

WORKDIR /app

# Install 'serve' globally to handle SPA routing (redirecting routes to index.html)
RUN npm install -g serve

# Copy built files from stage 1
COPY --from=build /app/dist ./dist

# Render sets the PORT env variable automatically. We expose a default port (80)
# but run 'serve' dynamically binding to the port designated by the platform.
ENV PORT=80
EXPOSE 80

# Run 'serve' in single-page-application mode (-s) to support React Router path routing
CMD ["sh", "-c", "serve -s dist -l $PORT"]
