import globals from 'globals';
export default [{files:['renmon/static/**/*.js'], languageOptions:{ecmaVersion:'latest',sourceType:'module',globals:globals.browser},rules:{'no-undef':'error','no-unused-vars':['error',{args:'none',caughtErrors:'none'}],'no-unreachable':'error','no-duplicate-imports':'error'}}];
